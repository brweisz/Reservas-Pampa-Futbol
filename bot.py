import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright, BrowserContext, Page
from notificacion import enviar_notificacion

INTERVALO_SEGUNDOS = 30

SELECTOR_CARDS = ".MuiGrid-item.MuiGrid-grid-xs-12"

# Shared browser instance for the web service (set by app/main.py)
_browser = None


async def get_browser():
    global _browser
    if _browser is None or not _browser.is_connected():
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=True)
    return _browser


async def obtener_clases(page: Page) -> list[dict]:
    cards = page.locator(SELECTOR_CARDS)
    count = await cards.count()
    clases = []
    for i in range(count):
        card = cards.nth(i)

        nivel_el = card.locator("text.sc-fLlhyt").first
        fecha_el = card.locator("text").filter(has_text="\U0001f5d3\ufe0f").first
        sede_el = card.locator("strong").first
        disp_el = card.locator("text").filter(has_text="lugar").first
        chip_el = card.locator(".MuiChip-root").first

        nivel = (await nivel_el.inner_text()).strip() if await nivel_el.count() > 0 else ""
        fecha = (await fecha_el.inner_text()).strip() if await fecha_el.count() > 0 else ""
        sede = (await sede_el.inner_text()).strip() if await sede_el.count() > 0 else ""
        disponibilidad = (await disp_el.inner_text()).strip() if await disp_el.count() > 0 else ""

        cancha = ""
        if await sede_el.count() > 0:
            location_text = await sede_el.evaluate("el => el.parentElement.innerText")
            parts = location_text.strip().split("\n- ", 1)
            if len(parts) > 1:
                cancha = parts[1].strip()

        disponible = False
        if await chip_el.count() > 0:
            aria_disabled = await chip_el.get_attribute("aria-disabled")
            disponible = aria_disabled != "true"

        clases.append({
            "index": i,
            "nivel": nivel,
            "fecha": fecha,
            "sede": sede,
            "cancha": cancha,
            "disponibilidad": disponibilidad,
            "disponible": disponible,
        })
    return clases


async def login(documento: str, password: str) -> BrowserContext:
    """Log in to pampafutbol.com and return the authenticated browser context."""
    browser = await get_browser()
    context = await browser.new_context()
    page = await context.new_page()

    await page.goto("https://www.pampafutbol.com/login")
    await page.wait_for_selector("#documento", timeout=15000)
    await page.fill("#documento", documento)
    await page.fill("#password", password)
    await page.click('button[type="submit"]')

    try:
        await page.wait_for_url("https://www.pampafutbol.com", timeout=10000)
    except Exception:
        await context.close()
        raise RuntimeError("Login failed — check documento and password.")

    return context


async def list_classes(context: BrowserContext) -> list[dict]:
    """Navigate to the class listing and return all available classes."""
    page = context.pages[0]
    await page.goto("https://www.pampafutbol.com/alumno/clases-disponibles")
    await page.wait_for_selector(SELECTOR_CARDS, timeout=15000)
    return await obtener_clases(page)


async def _try_book(page, target_fecha, target_nivel, target_sede, on_success):
    """Check the current page for the target class and book it if available.
    Returns True if booked, False if not available, None if class not found."""
    clases = await obtener_clases(page)
    for clase in clases:
        if (clase["fecha"] == target_fecha
                and clase["nivel"] == target_nivel
                and clase["sede"] == target_sede):
            if clase["disponible"]:
                chip = page.locator(SELECTOR_CARDS).nth(clase["index"]).locator(".MuiChip-root").first
                await chip.click()
                await asyncio.sleep(5)
                if on_success:
                    await on_success(clase)
                return True
            return False
    return None


async def poll_and_book(
    context: BrowserContext,
    class_tuple: dict,
    on_success=None,
    on_error=None,
) -> None:
    """Book the chosen class immediately if available, otherwise poll until it opens."""
    page = context.pages[0]
    target_fecha = class_tuple["fecha"]
    target_nivel = class_tuple["nivel"]
    target_sede = class_tuple["sede"]

    # Try booking with the already-loaded page (from list_classes)
    result = await _try_book(page, target_fecha, target_nivel, target_sede, on_success)
    if result is True:
        return
    if result is None:
        print("  Class not found in listing (may have changed).")

    # Not available yet — enter polling loop
    intento = 1
    while True:
        await asyncio.sleep(INTERVALO_SEGUNDOS)
        await page.reload()
        await page.wait_for_selector(SELECTOR_CARDS, timeout=15000)

        result = await _try_book(page, target_fecha, target_nivel, target_sede, on_success)
        if result is True:
            return
        if result is None:
            print(f"  [Attempt {intento}] Class not found in listing (may have changed).")

        intento += 1


# --------------- CLI entry point (preserves original behavior) ---------------

async def _cli_main():
    load_dotenv()
    documento = os.environ["DOCUMENTO"]
    password = os.environ["PASSWORD"]

    print("Iniciando sesion...")
    context = await login(documento, password)
    print("Sesion iniciada correctamente.\n")

    clases = await list_classes(context)

    if not clases:
        print("No se encontraron clases.")
        await context.close()
        return

    print("=== CLASES DISPONIBLES ===\n")
    for i, clase in enumerate(clases):
        estado = "Con lugar" if clase["disponible"] else "Sin lugar"
        print(f"  [{i + 1}] {clase['fecha']} | {clase['nivel']} | {clase['sede']}")
        print(f"       {clase['disponibilidad']} -- {estado}\n")

    while True:
        try:
            opcion = int(input("Elegi el numero de la clase a reservar: ")) - 1
            if 0 <= opcion < len(clases):
                break
        except (ValueError, KeyboardInterrupt):
            pass
        print("Opcion invalida, ingresa un numero de la lista.")

    elegida = clases[opcion]
    print(f"\nObjetivo: {elegida['fecha']} | {elegida['nivel']} | {elegida['sede']}")
    print(f"Revisando cada {INTERVALO_SEGUNDOS} segundos...\n")

    async def _on_success(clase):
        print("\nClase reservada!")
        try:
            enviar_notificacion(clase)
            print(f"Notificacion enviada a {os.environ['MAIL_TO']}.")
        except Exception as e:
            print(f"No se pudo enviar la notificacion: {e}")

    await poll_and_book(context, elegida, on_success=_on_success)
    await context.close()


if __name__ == "__main__":
    asyncio.run(_cli_main())

import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DOCUMENTO = os.environ["DOCUMENTO"]
PASSWORD = os.environ["PASSWORD"]

INTERVALO_SEGUNDOS = 30

SELECTOR_CARDS = ".MuiGrid-item.MuiGrid-grid-xs-12"


async def obtener_clases(page):
    cards = page.locator(SELECTOR_CARDS)
    count = await cards.count()
    clases = []
    for i in range(count):
        card = cards.nth(i)

        # "text" es el tag HTML usado por styled-components para labels; no hay
        # equivalente MUI para nivel, así que se filtra por contenido estable.
        nivel_el = card.locator("text.sc-fLlhyt").first
        fecha_el = card.locator("text").filter(has_text="🗓️").first
        sede_el = card.locator("strong").first
        disp_el = card.locator("text").filter(has_text="lugar").first
        chip_el = card.locator(".MuiChip-root").first

        nivel = (await nivel_el.inner_text()).strip() if await nivel_el.count() > 0 else ""
        fecha = (await fecha_el.inner_text()).strip() if await fecha_el.count() > 0 else ""
        sede = (await sede_el.inner_text()).strip() if await sede_el.count() > 0 else ""
        disponibilidad = (await disp_el.inner_text()).strip() if await disp_el.count() > 0 else ""

        disponible = False
        if await chip_el.count() > 0:
            aria_disabled = await chip_el.get_attribute("aria-disabled")
            disponible = aria_disabled != "true"

        clases.append({
            "index": i,
            "nivel": nivel,
            "fecha": fecha,
            "sede": sede,
            "disponibilidad": disponibilidad,
            "disponible": disponible,
        })
    return clases


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # --- Login ---
        print("Iniciando sesión...")
        await page.goto("https://www.pampafutbol.com/login")
        await page.wait_for_selector("#documento", timeout=15000)
        await page.fill("#documento", DOCUMENTO)
        await page.fill("#password", PASSWORD)
        await page.click('button[type="submit"]')

        try:
            await page.wait_for_url("https://www.pampafutbol.com", timeout=10000)
        except Exception:
            print("Error: no se pudo iniciar sesión. Verificá documento y contraseña.")
            await browser.close()
            return

        print("Sesión iniciada correctamente.\n")

        # --- Cargar clases ---
        await page.goto("https://www.pampafutbol.com/alumno/clases-disponibles")
        await page.wait_for_selector(SELECTOR_CARDS, timeout=15000)

        clases = await obtener_clases(page)

        if not clases:
            print("No se encontraron clases.")
            await browser.close()
            return

        # --- Mostrar opciones ---
        print("=== CLASES DISPONIBLES ===\n")
        for i, clase in enumerate(clases):
            estado = "✅ Con lugar" if clase["disponible"] else "❌ Sin lugar"
            print(f"  [{i + 1}] {clase['fecha']} | {clase['nivel']} | {clase['sede']}")
            print(f"       {clase['disponibilidad']} — {estado}\n")

        # --- Elegir clase ---
        while True:
            try:
                opcion = int(input("Elegí el número de la clase a reservar: ")) - 1
                if 0 <= opcion < len(clases):
                    break
            except (ValueError, KeyboardInterrupt):
                pass
            print("Opción inválida, ingresá un número de la lista.")

        elegida = clases[opcion]
        target_fecha = elegida["fecha"]
        target_nivel = elegida["nivel"]
        target_sede = elegida["sede"]

        print(f"\nObjetivo: {target_fecha} | {target_nivel} | {target_sede}")
        print(f"Revisando cada {INTERVALO_SEGUNDOS} segundos...\n")

        # --- Polling ---
        intento = 1
        while True:
            print(f"[Intento {intento}] Recargando página...")
            await page.reload()
            await page.wait_for_selector(SELECTOR_CARDS, timeout=15000)

            clases = await obtener_clases(page)

            encontrada = False
            for clase in clases:
                if (clase["fecha"] == target_fecha
                        and clase["nivel"] == target_nivel
                        and clase["sede"] == target_sede):
                    encontrada = True
                    print(f"  Estado: {clase['disponibilidad']}")

                    if clase["disponible"]:
                        print("\n¡Lugar disponible! Haciendo click en 'Recuperar'...")
                        chip = page.locator(SELECTOR_CARDS).nth(clase["index"]).locator(".MuiChip-root").first
                        await chip.click()
                        print("Click realizado. Esperando confirmación...")
                        await asyncio.sleep(5)
                        print("¡Listo! Verificá en el navegador que la reserva quedó confirmada.")
                        input("Presioná Enter para cerrar el navegador...")
                        await browser.close()
                        return
                    break

            if not encontrada:
                print("  Advertencia: no se encontró la clase en la página (puede haber cambiado el listado).")

            print(f"  Próximo intento en {INTERVALO_SEGUNDOS} segundos...")
            intento += 1
            await asyncio.sleep(INTERVALO_SEGUNDOS)


asyncio.run(main())

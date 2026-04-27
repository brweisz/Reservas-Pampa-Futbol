import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DOCUMENTO = os.environ["DOCUMENTO"]
PASSWORD = os.environ["PASSWORD"]

INTERVALO_SEGUNDOS = 30


async def obtener_clases(page):
    cards = await page.query_selector_all("div.sc-hHLeRK")
    clases = []
    for card in cards:
        nivel_el = await card.query_selector("text.sc-fLlhyt")
        fecha_el = await card.query_selector("text.sc-cxabCf")
        sede_el = await card.query_selector("span.sc-iIPllB strong")
        disp_el = await card.query_selector("text.sc-gicCDI")
        chip_el = await card.query_selector(".MuiChip-root")

        nivel = (await nivel_el.inner_text()).strip() if nivel_el else ""
        fecha = (await fecha_el.inner_text()).strip() if fecha_el else ""
        sede = (await sede_el.inner_text()).strip() if sede_el else ""
        disponibilidad = (await disp_el.inner_text()).strip() if disp_el else ""

        disponible = False
        if chip_el:
            aria_disabled = await chip_el.get_attribute("aria-disabled")
            disponible = aria_disabled != "true"

        clases.append({
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
            await page.wait_for_url("**/alumno/**", timeout=10000)
        except Exception:
            print("Error: no se pudo iniciar sesión. Verificá documento y contraseña.")
            await browser.close()
            return

        print("Sesión iniciada correctamente.\n")

        # --- Cargar clases ---
        await page.goto("https://www.pampafutbol.com/alumno/clases-disponibles")
        await page.wait_for_selector("div.sc-hHLeRK", timeout=15000)

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
            await page.wait_for_selector("div.sc-hHLeRK", timeout=15000)

            clases = await obtener_clases(page)

            encontrada = False
            for i, clase in enumerate(clases):
                if (clase["fecha"] == target_fecha
                        and clase["nivel"] == target_nivel
                        and clase["sede"] == target_sede):
                    encontrada = True
                    print(f"  Estado: {clase['disponibilidad']}")

                    if clase["disponible"]:
                        print("\n¡Lugar disponible! Haciendo click en 'Recuperar'...")
                        cards = await page.query_selector_all("div.sc-hHLeRK")
                        chip = await cards[i].query_selector(".MuiChip-root")
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

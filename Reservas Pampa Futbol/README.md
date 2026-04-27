# Bot de reservas - Pampa Fútbol

Reserva automáticamente una clase en [pampafutbol.com](https://www.pampafutbol.com). Recarga la página cada 30 segundos hasta que se habilite un lugar y hace el click automáticamente.

## Instalación

```bash
bash setup.sh
```
o
```bash
./setup.sh
```

En caso de error de permisos, ejecutar antes

```bash
sudo chmod +x setup.sh
```


## Configuración

Editá el archivo `.env` con tus credenciales:

```
DOCUMENTO=12345678
PASSWORD=tupassword
```

## Uso

```bash
python bot.py
```

1. El bot inicia sesión y muestra todas las clases disponibles
2. Elegís el número de la clase que querés reservar
3. El bot recarga la página cada 30 segundos hasta que haya lugar
4. Cuando se habilita un lugar, hace el click automáticamente y termina

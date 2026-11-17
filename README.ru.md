<p align="center"><a href="README.md">English</a> · <a href="README.ru.md">Русский</a></p>
<h1 align="center">Photonicat Companion</h1>
<p align="center">Мониторинг роутера, управление устройством и VPN с Android, macOS и Windows.</p>
<p align="center"><img alt="Flutter" src="https://img.shields.io/badge/Flutter-f4e600?style=flat-square"> <img alt="Python" src="https://img.shields.io/badge/Python-f4e600?style=flat-square"> <img alt="Bluetooth LE" src="https://img.shields.io/badge/Bluetooth%20LE-f4e600?style=flat-square"></p>

<p align="center">
<img src="docs/readme/current-status.png" width="30%" alt="Status demo">
<img src="docs/readme/current-vpn.png" width="30%" alt="Current Direct / VPN controls">
<img src="docs/readme/current-controls.png" width="30%" alt="Current screen and fan controls">
</p>
> Пример экранов Android. Данные вымышлены; настольная версия выглядит немного иначе.

## Твой роутер — под рукой

Photonicat Companion показывает состояние Photonicat 2 и позволяет управлять Wi-Fi, VPN, экраном и вентилятором. На телефоне связь идёт по Bluetooth. На компьютере — по Wi-Fi или кабелю, а приложение открывается из значка рядом с часами.

### Скачать 0.7.5 beta

| Устройство | Скачать |
| --- | --- |
| Android 12 и новее | [APK](https://github.com/svllvsxprod/photonicat-companion/releases/download/v0.7.5-beta.1/Photonicat-0.7.5-Android.apk) |
| Mac с Apple Silicon, macOS 12 и новее | [DMG](https://github.com/svllvsxprod/photonicat-companion/releases/download/v0.7.5-beta.1/Photonicat-0.7.5-beta.1-macOS-AppleSilicon.dmg) |
| Windows x64 | [Установщик EXE](https://github.com/svllvsxprod/photonicat-companion/releases/download/v0.7.5-beta.1/Photonicat-0.7.5-Windows-x64-Setup.exe) |

[Все файлы и описание выпуска →](https://github.com/svllvsxprod/photonicat-companion/releases/tag/v0.7.5-beta.1)

Это тестовая версия. Система может предупредить о подписи установщика; подробности указаны в описании выпуска. iPhone пока не поддерживается.

### Что умеет

- Показывает заряд, температуру, скорость интернета, загрузку процессора и памяти.
- Управляет Wi-Fi, яркостью экрана и вентилятором.
- Добавляет подписки Mihomo и профили AmneziaWG, переключает обычный интернет и VPN.
- Показывает подключённые устройства и входящие СМС.
- Помогает установить службу управления на роутер через мастер на компьютере.

**Новое в 0.7.5:** на Mac и Windows приложение само восстанавливает связь при переходе с Wi-Fi на кабель и обратно. Повторно вводить ключ не нужно.

### Как начать

1. Установи приложение на компьютер и подключись к Wi-Fi или LAN роутера.
2. Нажми значок кота → **«Настроить роутер»**. Мастер попросит адрес роутера и пароль администратора.
3. Пройди настройку и сохрани выданный ключ. Для телефона установи APK и введи тот же ключ в приложении.

[Настройка с нуля: пошагово и со скриншотами →](docs/public/SETUP_RU.md)

[Установка на телефон, VPN и решение проблем →](docs/public/USAGE_RU.md)

Мастер рассчитан на Photonicat 2 с PhotonicatWrt 26.04.1. Полная установка на роутер из коробки ещё требует проверки. В приложении нет чужих ключей или готовой VPN-подписки — используются только твои.

### О проекте

Независимое приложение, не официальный продукт Photonicat. [Исходники и сборка](docs/public/BUILD.md) · [Права и лицензии](RIGHTS.md). Исходники опубликованы для ознакомления; общая лицензия на их повторное использование пока не выбрана.

---

<p align="center">
<a href="https://t.me/tribute/app?startapp=dK9j"><img src="docs/readme/support-tribute.svg" height="36" alt="Support via Tribute"></a>
<a href="https://nowpayments.io/donation/svllvsx"><img src="docs/readme/support-nowpayments.svg" height="36" alt="Support via NOWPayments"></a>
<a href="https://t.me/svllvsxprod"><img src="docs/readme/telegram.svg" height="36" alt="Telegram"></a>
</p>

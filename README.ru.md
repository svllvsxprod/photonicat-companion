<p align="center"><a href="README.md">English</a> · <a href="README.ru.md">Русский</a></p>
<h1 align="center">Photonicat Companion</h1>
<p align="center">Мониторинг роутера, управление устройством и VPN с Android, macOS и Windows.</p>
<p align="center"><img alt="Flutter" src="https://img.shields.io/badge/Flutter-f4e600?style=flat-square"> <img alt="Python" src="https://img.shields.io/badge/Python-f4e600?style=flat-square"> <img alt="Bluetooth LE" src="https://img.shields.io/badge/Bluetooth%20LE-f4e600?style=flat-square"></p>

<p align="center">
<img src="docs/readme/current-status.png" width="30%" alt="Status demo">
<img src="docs/readme/current-vpn.png" width="30%" alt="Current Direct / VPN controls">
<img src="docs/readme/current-controls.png" width="30%" alt="Current screen and fan controls">
</p>
> Иллюстрации Android-версии до настольного выпуска: виджеты отрисованы 21.10.2026 в изолированном демо-окружении. Показатели, имена и адреса вымышлены; брендинг заменён. Это не замер работающего устройства.

## Версия 0.7.5 beta

[**Скачать APK, DMG для Mac и EXE для Windows**](https://github.com/svllvsxprod/photonicat-companion/releases/tag/v0.7.5-beta.1) · [Мастер настройки со скриншотами](docs/public/SETUP_RU.md) · [Установка и повседневное управление](docs/public/USAGE_RU.md)

Приложение на компьютере восстанавливает связь при переходе **Wi-Fi ↔ Ethernet**. Поиск учитывает шлюзы всех активных адаптеров и проверяет сохранённый ключ роутера. Команды, прерванные обрывом, автоматически не повторяются.

| Возможность | Реализация |
| --- | --- |
| Android 12+ | Управление по Bluetooth LE с защищённой привязкой; APK в релизе. |
| macOS 12+, Apple Silicon | Панель из строки меню, связь по локальной сети; автозапуск по выбору с macOS 13. |
| Windows x64 | Панель из трея с учётом экрана, автозапуск по выбору, установщик и portable ZIP. |
| Первая настройка | Компьютерный мастер обнаруживает оборудование, устанавливает службу и получает ключ роутера. |
| VPN | Подписки Mihomo, профили AmneziaWG, один выбранный профиль на каждом ядре, режимы Direct/VPN. |
| Пять разделов | Состояние, устройства, VPN, роутер и входящие СМС. |
| Управление | Wi-Fi, яркость и таймер экрана, вентилятор; батарея, CPU, RAM и трафик. |

GearUP из приложения удалён. Мастер не прошивает модем и не устанавливает неизвестные драйверы.

## С чего начать

1. Подключите компьютер к клиентской сети Photonicat по Wi-Fi или Ethernet.
2. Установите приложение, откройте значок кота и нажмите **«Настроить роутер»**. Понадобятся локальный адрес роутера и административный пароль SSH.
3. Пройдите [мастер со скриншотами](docs/public/SETUP_RU.md) и сохраните ключ привязки в менеджере паролей.
4. На Android установите APK, включите Bluetooth, вставьте этот ключ и разрешите доступ к устройствам поблизости. Телефон управляет по BLE; первичная установка службы выполняется с компьютера.
5. Добавьте собственную VPN-подписку/конфигурацию и выберите Direct или VPN для нужного клиентского подключения.

Ключей владельца, личных подписок и конфигурации действующего роутера в выпуске нет. Обновление совместимой сборки устанавливается поверх прежней; перед удалением приложения сохраните ключ.

## Исходники и сборка

| Каталог | Содержимое |
| --- | --- |
| `mobile/` | Общий Flutter-интерфейс, проекты Android/iOS/macOS/Windows и тесты. |
| `router/ · vpn-service/` | Защищённая служба BLE/LAN, мониторинг, управление и VPN. |
| `installer/` | Проверки совместимости и установка с подтверждением результата. |
| `docs/public/` | Инструкции со скриншотами и описание выпуска. |
| `tools/` | Сборка настольных приложений и экспорт разрешённых исходников. |

Используются Flutter 3.44.2 / Dart 3.12.2. Для Mac нужен Xcode; для Windows — Visual Studio с C++ и Inno Setup 6.3+; для Android — Android SDK и JDK 17. Android release сейчас использует локальную тестовую подпись. Для своей раздачи настройте собственную подпись и не сохраняйте keystore в Git.

```sh
cd mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --release
# Из корня проекта на соответствующей ОС:
# bash tools/build-macos.sh
# pwsh -File tools/build-windows.ps1
```

Для Python создайте изолированное окружение, установите `requirements-dev.txt` и запустите `python -m unittest discover -s tests`, `python -m unittest discover -s tests/setup` и `python -m unittest discover -s vpn-service -p 'test_*.py'`. Проверенный пакет служб включён в исходники; для пересборки из закреплённых upstream-компонентов используйте `tools/build-public-payload.py` с установленным Go. Утилита подготовки телефона `tools/provision_phone.py` принимает `PHOTONICAT_SSH_TARGET` и необязательный `ADB`; она не запускается при обычной сборке.

## Что проверено и что ещё нет

Для настольной версии прошли анализ и 39 Flutter-тестов на Mac и Windows. Реальная связь с роутером восстановилась после имитации потери адаптера без изменения сети ОС. Физическое переключение Wi-Fi/кабеля в этом выпуске не выполнялось. В Windows-среде прошли установка, скрытый запуск и удаление; это не заменяет проверку настоящего ПК с роутером. APK собран, подпись проверена; запуск именно нового APK на телефоне при подготовке релиза не проверен.

Мастер рассчитан на Photonicat 2 с PhotonicatWrt 26.04.1; полный путь на заводском устройстве пока не подтверждён. iOS включён в исходники, но проверенного выпуска нет. Протокол не проходил независимый аудит. EXE пока без подписи, Mac — с подписью разработки Apple без нотариализации, APK — с текущим тестовым сертификатом. [Подробности выпуска](docs/public/RELEASE_0_7_5.md).

## Права и зависимости

Исходники опубликованы для ознакомления. Общая лицензия на повторное использование собственного кода не выбрана. Сторонние компоненты сохраняют свои условия: [RIGHTS.md](RIGHTS.md). К выпуску приложены соответствующие исходники Mihomo/AmneziaWG и лицензии. Это независимый проект, не продукт производителя роутера.

---

<p align="center">
<a href="https://t.me/tribute/app?startapp=dK9j"><img src="docs/readme/support-tribute.svg" height="36" alt="Support via Tribute"></a>
<a href="https://nowpayments.io/donation/svllvsx"><img src="docs/readme/support-nowpayments.svg" height="36" alt="Support via NOWPayments"></a>
<a href="https://t.me/svllvsxprod"><img src="docs/readme/telegram.svg" height="36" alt="Telegram"></a>
</p>

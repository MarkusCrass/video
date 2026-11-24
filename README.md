# 🎬 Reels & Shorts Studio

Веб-студия на **Streamlit** для создания вертикальных видео **1080×1920 (9:16)** под
Instagram Reels, YouTube Shorts, TikTok и ВК Клипы.

- **Авто-генератор** — находит ролики на YouTube по запросу, скачивает (`yt-dlp`), нарезает
  1–15 роликов по 7–25 секунд, умно кадрирует 9:16 (размытый фон или центр-кроп), добавляет
  музыку, заголовок и призыв к действию. Три пресета в один клик.
- **Студия монтажа и озвучки** — обрезка, запись голоса с микрофона (или загрузка диктофона),
  автоматическое приглушение музыки до 13 % под голосом, текст на экране (белый / золотой /
  чёрный на плашке), финальный рендер.
- **Библиотека треков** — загрузка своих MP3/WAV (например, из Suno), плеер и удаление.
- **Безопасность** — вход по паролю (`APP_PASSWORD`), ограничение попыток, контроль места на диске,
  очистка временных файлов и автоматическое удаление исходников старше 24 часов.

Текст и эмодзи накладываются через **Pillow** (PNG с прозрачностью) и `overlay` в ffmpeg,
поэтому кириллица и переносы строк работают одинаково на Windows, macOS и Linux.

---

## 1. Требования

- Python **3.10+**
- Интернет-доступ к YouTube (для генератора)
- `ffmpeg` **не обязателен**: если системного нет, используется бинарник из пакета `imageio-ffmpeg`.
- Шрифт `DejaVuSans-Bold.ttf` уже лежит в `assets/fonts/`. Если хотите использовать системный —
  `sudo apt install fonts-dejavu-core`.
- Эмодзи в тексте (🌙 👇) — установите `fonts-noto-color-emoji`. Без него эмодзи пропускаются,
  и на видео не появляются пустые квадраты.

## 2. Локальный запуск (Windows / macOS / Linux)

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
streamlit run app.py
```

Откройте <http://localhost:8501>. Пароль по умолчанию — `moon2026` (меняется в `.env`).

Чтобы открыть приложение с телефона в той же Wi-Fi-сети, используйте IP компьютера:
`http://192.168.x.x:8501`.

## 3. Развёртывание на Ubuntu VPS (24/7, доступ по IP:порт)

```bash
# 1. Системные пакеты
sudo apt update
sudo apt install -y python3-venv python3-pip fonts-dejavu-core fonts-noto-color-emoji nodejs

# 2. Код приложения
sudo mkdir -p /opt/reels_studio && sudo chown $USER:$USER /opt/reels_studio
git clone https://github.com/MarkusCrass/video.git /opt/reels_studio
cd /opt/reels_studio
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Пароль и порт
cp .env.example .env
nano .env                       # APP_PASSWORD=ваш_пароль, PORT=8501

# 4. Служба systemd (автозапуск, перезапуск при падении)
sudo cp reels_studio.service /etc/systemd/system/
sudo sed -i "s/^User=.*/User=$USER/; s/^Group=.*/Group=$USER/" /etc/systemd/system/reels_studio.service
sudo systemctl daemon-reload
sudo systemctl enable --now reels_studio
sudo systemctl status reels_studio

# 5. Открыть порт (если включён ufw)
sudo ufw allow 8501/tcp
```

Приложение будет доступно по адресу `http://<IP-сервера>:8501` с ПК и смартфона.
Служба запускается на `0.0.0.0:8501` с `--server.maxUploadSize=500` (загрузка файлов до 500 МБ).

Обновление: `git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart reels_studio`.

Логи: `journalctl -u reels_studio -f`.

> **Важно про безопасность.** Доступ по IP:порт работает по HTTP. Пароль защищает интерфейс,
> но трафик не шифруется. Для постоянной работы рекомендуем поставить перед приложением
> HTTPS-прокси (Caddy или Nginx + Let's Encrypt) или ограничить порт 8501 своим IP через ufw.

## 4. Переменные окружения (`.env`)

| Переменная       | По умолчанию | Назначение                                              |
|------------------|--------------|---------------------------------------------------------|
| `APP_PASSWORD`   | `moon2026`   | Пароль входа                                            |
| `PORT`           | `8501`       | Порт (для systemd-службы нужно менять и в unit-файле)   |
| `STUDIO_DATA_DIR`| папка проекта| Куда писать `music/`, `output/`, `tmp/`                 |
| `MUSIC_DIR`      | `music/`     | Папка с треками                                         |
| `FONT_PATH`      | авто         | Свой TTF-шрифт для текста (Cyrillic)                    |
| `EMOJI_FONT_PATH`| авто         | Свой цветной эмодзи-шрифт (`NotoColorEmoji.ttf`)        |

## 5. Как работает генератор

1. Поиск YouTube через `python -m yt_dlp` (берётся до 40 результатов).
2. Ролики длиннее **15 минут**, недоступные, живые трансляции и повреждённые файлы **пропускаются**;
   берётся следующий результат из выдачи.
3. Каждый источник → один ролик. Для многосценовых пресетов (сериалы, CS2) сцены выбираются
   по точкам смены кадра, так что в ролик попадают динамичные моменты.
4. Кадрирование: **Blur** (16:9 по центру, сверху и снизу размытая копия того же кадра)
   или **Center Crop** (полный экран по центру).
5. Музыка из `music/` (случайный трек или выбранный), громкость задаётся ползунками.

Готовые ролики лежат в `output/`. Кнопка **«✂️ Открыть в редакторе»** передаёт ролик в редактор.

## 6. Временные файлы и место на диске

- В сайдбаре показываются свободное место, объём временных файлов и кнопка
  **🧹 Очистить временные файлы** (очищает `tmp/`: исходники, промежуточные клипы, загрузки).
- При каждом обновлении страницы автоматически удаляются временные файлы старше **24 часов**.
- Готовые ролики в `output/` не удаляются автоматически — удаляйте их вручную, когда они не нужны.

## 7. Тесты

```bash
python -m py_compile app.py studio/*.py studio/ui/*.py tests/*.py
python -m unittest discover -s tests -p "test_core.py" -v   # логика, ffmpeg, пайплайн
python -m unittest discover -s tests -p "test_app.py" -v    # UI через Streamlit AppTest
```

Тесты используют синтетические видео (ffmpeg) во временной папке и не трогают ваши файлы.
YouTube в тестах подменяется фикстурами, поэтому они работают без доступа к интернету.

## 8. Частые проблемы

- **«Поиск YouTube не удался» / «Sign in to confirm»** — обновите yt-dlp:
  `.venv/bin/pip install -U yt-dlp`. Для YouTube часто нужен JavaScript-рантайм: установите `nodejs`.
- **Текст без кириллицы / квадраты** — установите `fonts-dejavu-core` или укажите `FONT_PATH`.
- **Эмодзи не видны** — установите `fonts-noto-color-emoji` и перезапустите службу.
- **Ошибка загрузки большого файла** — проверьте `--server.maxUploadSize=500` в unit-файле и
  лимит вашего веб-прокси (например, `client_max_body_size` в Nginx).

## 9. Структура проекта

```
app.py                   точка входа Streamlit (вход по паролю, вкладки)
studio/
  config.py              пути, лимиты, шрифты, переменные окружения
  security.py            проверка пароля, блокировка после неудачных попыток
  storage.py             место на диске, очистка временных файлов, список роликов
  ffmpeg_tools.py        поиск ffmpeg, probe, запуск ffmpeg, поиск сцен
  textart.py             текст на Pillow → прозрачный PNG 1080×1920
  youtube.py             поиск и скачивание через yt-dlp
  renderer.py            кадрирование 9:16, сборка сцен, финальный микшер
  generator.py           пакетная генерация (поиск → скачивание → монтаж)
  editor.py              редактор: обрезка, текст, озвучка с дакингом
  music.py               библиотека треков
  presets.py             три пресета генератора
  theme.py               тёмная тема (CSS)
  ui/                    вкладки и сайдбар
assets/fonts/            DejaVuSans-Bold.ttf (+ лицензия)
.streamlit/config.toml   тема и параметры сервера
reels_studio.service     unit-файл systemd
requirements.txt         зависимости
.env.example             пример настроек
tests/                   unit- и UI-тесты
```

## Лицензия и ответственность

Скачивание видео с YouTube регулируется условиями сервиса и авторским правом. Используйте
генератор только с материалами, на которые у вас есть права или разрешение.

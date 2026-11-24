# ФармаПлюс

Навчальна онлайн-аптека на Django. Відвідувач переглядає каталог і шукає товари. Покупець після входу змінює кошик, оформлює замовлення та переглядає власні квитанції. Демонстраційний режим картки дозволяє перевірити зміну статусу без банківських реквізитів.

## Запуск на Windows у PowerShell

Для перевіреної конфігурації потрібен Python 3.12. Команди виконуються з каталогу, де лежить manage.py.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:DJANGO_SECRET_KEY = (.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(64))")
$env:DJANGO_DEBUG = "1"
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_data
.venv\Scripts\python manage.py runserver
```

Відкрийте http://127.0.0.1:8000/ і зареєструйте навчальний обліковий запис. Для панелі /admin/ створіть окремого адміністратора командою `.venv\Scripts\python manage.py createsuperuser`.

## Linux та macOS

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

Ключ передається через середовище. Для постійної інсталяції збережіть один згенерований ключ у менеджері секретів і надавайте його кожному процесу. Режим налагодження вмикається лише явно для локальної розробки. Додаткові дозволені імена хостів задаються списком через кому у `DJANGO_ALLOWED_HOSTS`.

## Перевірка

Виконайте `python manage.py test` у віртуальному середовищі з установленим ключем. Для поіменного протоколу використовуйте `python manage.py test --verbosity 2`. Django створить окрему тестову базу SQLite. Відповідні тести містяться у `pharmacy/tests.py`.

## Коміти перевіреної версії

Поряд із вихідними файлами в архіві є coursework.bundle. Він містить гілку coursework із виправленнями поверх початкового коміту c795e68 репозиторію pharmaplus-. У вже клонованому початковому репозиторії імпортуйте гілку командою `git fetch "/шлях/до/coursework.bundle" refs/heads/coursework:refs/heads/coursework`, далі виконайте `git switch coursework`. Для звичайного запуску достатньо розпакованих вихідних файлів.

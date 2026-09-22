# Grocery Shop API (FastAPI)

Бэкенд интернет-магазина продуктов: каталог, поиск, регистрация/JWT, корзина, заказы, оплата (заглушка), админ-API.

## Запуск (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # и поменяйте SECRET_KEY / ADMIN_PASSWORD
python -m app.seed            # демо-данные (по желанию)
uvicorn app.main:app --reload
```

Сайт (фронтенд из папки `frontend/`): http://localhost:8000 · Swagger UI: http://localhost:8000/docs · тесты: `pytest`

Администратор создаётся при старте из `ADMIN_EMAIL` / `ADMIN_PASSWORD` в `.env`.

## API

| Область | Эндпоинты |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login` (form: username=email), `GET/PATCH /users/me` |
| Каталог | `GET /categories`, `GET /products` (`q, category_id, min_price, max_price, in_stock, sort, page, size`), `GET /products/{id}` |
| Корзина | `GET /cart`, `POST /cart/items`, `PATCH/DELETE /cart/items/{product_id}`, `DELETE /cart` |
| Заказы | `POST /orders`, `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel`, `POST /orders/{id}/pay` |
| Админ | `/admin/categories`, `/admin/products` (CRUD, мягкое удаление), `GET /admin/orders`, `PATCH /admin/orders/{id}/status`, `GET /admin/stats` |

## Доступ с других устройств

**В своей Wi-Fi сети (сразу, без регистраций):** узнайте IP компьютера через `ipconfig` (строка IPv4), разрешите порт в firewall

```powershell
New-NetFirewallRule -DisplayName "FastAPI 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

и запускайте сервер на всех интерфейсах:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

С телефона/ноутбука в той же сети зайдите на `http://<IP компьютера>:8000`. Работает, только пока компьютер включён и устройство в той же сети.

**Из интернета, бесплатно (Render + Neon):**

1. **База данных.** Зарегистрируйтесь на [neon.tech](https://neon.tech) (бесплатно, карта не нужна), создайте проект и скопируйте Connection string (вида `postgresql://user:pass@host/db?sslmode=require`) — код сам подставит нужный драйвер.
2. **Код на GitHub.** Загрузите папку проекта в новый репозиторий на [github.com](https://github.com) (через `git push` или кнопку "Add file → Upload files" в браузере, если Git не установлен). `.venv`, `.env` и `shop.db` туда не попадут — они в `.gitignore`.
3. **Сервер.** Зарегистрируйтесь на [render.com](https://render.com), New → Web Service → выберите репозиторий. В проекте уже лежит `render.yaml`, Render подхватит настройки сам. Задайте переменные окружения в панели Render:
   - `DATABASE_URL` — строка из Neon;
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD` — данные администратора;
   - `SECRET_KEY` Render сгенерирует сам.
4. Через пару минут сайт будет на адресе вида `https://ваш-проект.onrender.com` — открывается с любого устройства.

Особенность бесплатного плана Render: сервис «засыпает» после 15 минут без запросов, первый заход после этого — около минуты.

## Ключевые решения

- Товар резервируется при создании заказа атомарным `UPDATE ... WHERE stock >= qty` — нет перепродажи при параллельных заказах; отмена возвращает остатки.
- Заказ хранит снимок названия и цены (`OrderItem`), поэтому смена цены не портит историю.
- Деньги — `Decimal`/`Numeric(10,2)` (в JSON приходят строками, например `"2.50"`).
- Пароли — scrypt (stdlib), токены — JWT.
- Оплата: токен `tok_fail` отклоняется, остальные проходят. Замените заглушку в `app/routers/orders.py` (`pay`) на реального провайдера.
- SQLite по умолчанию; для PostgreSQL задайте `DATABASE_URL=postgresql+psycopg://...` и установите драйвер. Для продакшена добавьте Alembic-миграции.

## Структура

```
app/  main.py config.py database.py models.py schemas.py security.py deps.py seed.py
      routers/  auth.py catalog.py cart.py orders.py admin.py
tests/test_api.py
```

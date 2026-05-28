# Платформа ВКР — техническая документация

Веб-система для автоматизации структурированных документов: загрузка DOCX-шаблонов, справочники, настраиваемые **шаблоны бизнес-процессов (БП)** с пошаговым мастером для оператора и генерацией DOCX.

## Стек

| Компонент | Версия / заметки |
|-----------|------------------|
| Python | 3.12+ |
| Django | 5.1.x |
| Django REST Framework | API под CRUD и интеграции |
| База данных | SQLite (файл `db.sqlite3`) |
| Шаблоны UI | Django Templates, встроенные стили в `templates/ui/base.html` |
| Документы | `python-docx` — извлечение плейсхолдеров и подстановка значений |

## Структура репозитория

```
backend/
  config/           # settings.py, urls.py, wsgi/asgi
  apps/
    bpm/            # Шаблоны БП, экземпляры, справочники, правила полей
    documents/      # Модель Documents, генерация HTML/DOCX, UI списка/превью
    templates_cfg/  # Типы документов (DocumentTypes), загрузка шаблонов, настройка полей
    requisites/     # Реквизиты, значения, связи (legacy-автозаполнение)
    processes/      # Процессы и шаги (совместимость с Documents.process_id)
    users/          # Пользователи, сессии UI, контекст current_enterprise_user
    roles/          # Роли ADMIN / SPECIALIST / OPERATOR
    logs/           # Журнал операций
  templates/ui/     # HTML-шаблоны интерфейса
  media/            # Загруженные DOCX и сгенерированные файлы
  manage.py
  requirements.txt
```

Корень репозитория `vkr/` может содержать краткий `README.md` со ссылкой на этот файл.

## Установка и запуск

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Полный сброс БД и повторная демо-заливка:

```bash
python manage.py reset_platform
```

## Архитектура приложений

### `apps.bpm`

Центральная логика сценария «шаблон БП → экземпляр → документы по шагам».

| Модель | Назначение |
|--------|------------|
| `BusinessProcessTemplate` | Имя, описание, связь с `processes.Processes` (`legacy_process`), опционально `objects_dictionary` |
| `ProcessDocumentTemplate` | Шаг: порядок, имя, `DocumentTypes` |
| `BusinessProcessInstance` | Запущенный БП: пользователь, `production_object`, статус, текущий шаг, `dictionary_record`, `context_json` |
| `ProcessDocumentInstance` | Связь экземпляра с `Documents` и конкретным шагом (`OneToOne` на документ) |
| `ReferenceDictionary` | Справочник; `selection_column_key` — колонка для отображения/выбора |
| `DictionaryColumn` | Ключ JSON + русское `title` |
| `DictionaryRecord` | `lookup_key` (уникален в паре с словарём), `payload_json` |
| `FieldSourceRule` | Для пары (шаг, реквизит): `source_type` manual / dictionary / previous_document (+ устаревшие enum в БД) |
| `InstanceDictionarySelection` | Выбранная запись по каждому словарю при старте |

Ключевые модули:

- `views.py` — UI шаблонов БП, старт экземпляра, мастер, ZIP всех DOCX при завершении, скачивание `download-all`.
- `services.py` — `resolve_fields_for_step`, `get_or_create_document_for_step`, `dictionaries_for_operator_startup`, `resolve_objects_dictionary_id`.
- `dictionary_pages.py` — CRUD справочников и записей для ролей ADMIN/SPECIALIST/OPERATOR, API поиска записей.
- `dict_keys.py` — вспомогательные функции для уникального `lookup_key`.

### `apps.templates_cfg`

- `DocumentTypes` — имя, описание, файл DOCX, кэш `template_html`.
- `ProductionObjects` — объект производства; может быть привязан к `DictionaryRecord` (`source_record`).
- UI: загрузка шаблона, настройка полей (**все реквизиты сохраняются как `field_kind=variable`** в каталоге), список типов на `/ui/document-types/`.

### `apps.documents`

- `Documents` — тип, процесс, объект, пользователь, статус, `generated_file`, `generated_html`.
- `generate_document()` — валидация обязательных полей, сборка HTML и DOCX.

### `apps.requisites`

- `Requisites` — привязка к типу документа, `placeholder_key`, `field_kind` (в каталоге после правок — преимущественно variable).
- `RequisiteValues`, `RequisiteLinks` — значения и наследование между типами (дополнительный путь автозаполнения в `resolve_fields_for_step`).

### `apps.processes`

- `Processes`, `ProcessSteps` — используются для совместимости и журнала; шаблон БП создаёт свой `Processes` при создании.

### `apps.users` / `apps.roles`

- Роли: `ADMIN`, `SPECIALIST`, `OPERATOR`.
- `LoginRequiredRoleMixin` + `allowed_roles` на class-based views.
- `context_processors.current_enterprise_user` — объект «текущий пользователь» в шаблонах.

## Потоки данных

### Проектирование (специалист)

1. Загрузка DOCX → создание `DocumentTypes` и `Requisites` из плейсхолдеров.
2. Уточнение подписей и обязательности на `/ui/templates/<id>/configure/`.
3. Создание шаблона БП, этапов (типы документов), при необходимости справочника объектов.
4. Настройка **правил полей** для каждого шага: ручной ввод, справочник (поле записи с русской подписью колонки), предыдущий документ.

### Запуск (оператор)

1. При наличии словарей в шаблоне — выбор записей (поиск через `DictionaryRecordsSearchJsonView`).
2. При отсутствии словарей — старт без выбора; `ProductionObjects` подставляется из служебной записи.
3. Мастер шага вызывает `resolve_fields_for_step` и отображает поля (в т.ч. read-only для автозаполнения).
4. Завершение: генерация DOCX по всем шагам, ответ — ZIP; повторное скачивание через `GET /ui/bpm/instance/<bpi_id>/download-all/`.

### Предпросмотр шаблона

- `GET /ui/templates/<document_type_id>/preview/?simple=1` — структура без классификации по БП.
- `GET .../preview/?bpt_id=&pdt_id=` — подсветка постоянный/переменный по `FieldSourceRule` шага.

## Маршруты UI (основные)

| Путь | Описание |
|------|----------|
| `/`, `/dashboard/` | Дашборд |
| `/login/`, `/logout/`, `/profile/`, `/register/` | Аутентификация |
| `/ui/help/` | Руководство пользователя |
| `/ui/document-types/` | Типы документов, поиск, редактирование метаданных |
| `/ui/templates/create/` | Загрузка DOCX |
| `/ui/templates/<id>/configure/` | Поля типа |
| `/ui/templates/<id>/preview/` | Предпросмотр |
| `/ui/bpm/process-templates/` | Список шаблонов БП |
| `/ui/bpm/process-templates/<bpt_id>/` | Настройка БП |
| `/ui/bpm/process-templates/<bpt_id>/steps/<pdt_id>/rules/` | Правила полей |
| `/ui/bpm/dictionaries/` | Справочники |
| `/ui/bpm/run/` | Хаб оператора |
| `/ui/bpm/run/<bpt_id>/start/` | Запуск экземпляра |
| `/ui/bpm/instance/<bpi_id>/` | Мастер |
| `/ui/bpm/instance/<bpi_id>/download-all/` | ZIP всех DOCX (завершённый экземпляр) |
| `/ui/documents/` | Реестр документов |
| `/ui/documents/<id>/preview/`, `/download/` | Просмотр и файл |

Полный список — `config/urls.py`.

## REST API

Роутер DRF (`/api/`) отдаёт ViewSet’ы для ролей, пользователей, типов документов, реквизитов, связей, процессов, шагов, документов, логов. Дополнительно:

- `POST /api/auth/login/`, `logout/`, `register/`, `GET /api/auth/me/`
- `POST /api/documents/<id>/generate/`, `autofill/`

Для отладки в `settings` по умолчанию разрешения DRF мягкие; в продакшене их нужно ужесточить.

## Конфигурация

Файл `config/settings.py`:

- `DATABASES` — SQLite в `BASE_DIR / db.sqlite3`.
- `MEDIA_ROOT` / `MEDIA_URL` — загрузки и генерация.
- `LANGUAGE_CODE = "ru-ru"`.
- Шаблоны: `DIRS = [BASE_DIR / "templates"]`.

## Расширение и сопровождение

- Новые поля БП — миграции в `apps.bpm` (и при необходимости в смежных приложениях).
- Изменение источников правил — модель `FieldSourceRule`, `apps.bpm.services.resolve_fields_for_step`.
- Сиды демо — `apps.users.management.commands.seed_demo`.

## Лицензия и авторство

Укажите по месту требований ВКР / организации.

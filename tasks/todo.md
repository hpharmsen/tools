# Todo App - Plan

## Context
Een supersnelle, minimalistische to-do app met native Mac-app en webversie, gesynchroniseerd via een API op harmsen.nl (Django, PostgreSQL, Heroku).

## Architectuur

```
Mac App (SwiftUI)  ──┐
                     ├──► Django API (harmsen.nl/todo/api/) ──► PostgreSQL
Web UI (harmsen.nl/todo/) ─┘
```

**Sync-strategie:** Eenvoudige JSON blob. Hele lijst wordt opgehaald/opgeslagen in 1 call. Last-write-wins met `updated_at` conflict-check.

## Data Model

Een enkel `TodoList` model met een `JSONField`:

```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Boodschappen",
      "details": "Melk, eieren\nhttps://example.com",
      "position": 0,
      "checked": false,
      "created_at": "2026-03-23T10:00:00Z",
      "updated_at": "2026-03-23T10:00:00Z"
    }
  ]
}
```

## Deel 1: Django API (~/Sites/Harmsen.nl)

Apps worden automatisch ontdekt in dit project - alleen een map aanmaken in `apps/` is voldoende.

### Nieuwe bestanden
- [ ] `~/Sites/Harmsen.nl/apps/todo/__init__.py`
- [ ] `~/Sites/Harmsen.nl/apps/todo/models.py` - TodoList model met JSONField
- [ ] `~/Sites/Harmsen.nl/apps/todo/views.py` - API views (GET/PUT) + web UI view
- [ ] `~/Sites/Harmsen.nl/apps/todo/urls.py` - URL routing
- [ ] Migrations draaien

### API Endpoints
- `GET /todo/api/` - Haal hele lijst op (Bearer token auth)
- `PUT /todo/api/` - Sla hele lijst op (Bearer token auth, conflict check via updated_at)
- `GET /todo/` - Web UI (self-contained HTML template)

### Auth
Simpele Bearer token via environment variable `TODO_API_TOKEN`. Geen user accounts nodig.

## Deel 2: Web UI (Django template)

- [ ] `~/Sites/Harmsen.nl/apps/todo/templates/todo/index.html` - Self-contained HTML met inline CSS/JS

### Design (Jony Ive stijl)
- Wit/lichtgrijs achtergrond, veel witruimte
- System font (`-apple-system, SF Pro`) in licht gewicht
- Dunne borders, subtiele schaduwen, afgeronde hoeken
- Eén accentkleur, verder alleen grijstinten
- Smooth 200ms transities

### Features
- Invoerbalk bovenin met Enter/knop support
- HTML5 native drag-and-drop voor herordenen (geen library nodig)
- Klik op item opent detail-editor met textarea (URLs worden linkbaar)
- Checkbox voor elk item - aanvinken verplaatst naar onderaan
- "Verwijder afgeronde" knop onderaan
- Debounced sync (500ms na laatste wijziging)

## Deel 3: Mac App (SwiftUI) - ~/proj/todo

Nieuw Xcode project in `~/proj/todo/`.

### Bestanden
- [ ] `TodoApp.swift` - App entry point
- [ ] `TodoItem.swift` - Codable struct
- [ ] `TodoViewModel.swift` - @Observable, API calls, lokale state
- [ ] `ContentView.swift` - Main view
- [ ] `TodoRowView.swift` - Item row met checkbox + drag
- [ ] `DetailEditor.swift` - Uitklapbare detail editor
- [ ] `APIService.swift` - URLSession wrapper

### Sync gedrag
- Fetch bij app launch en bij `willBecomeActive`
- Push na elke wijziging (debounced 500ms)
- Lokale JSON cache in `~/Library/Application Support/` als offline fallback

### Design
- `.listStyle(.plain)`, minimale chrome
- Licht font gewicht, muted kleuren
- Compact venster (~400x600)
- Hidden title bar voor clean look

## Deel 4: Deployment

- [ ] `TODO_API_TOKEN` instellen op Heroku
- [ ] Deployen via `./publish.sh`
- [ ] Mac app builden in Xcode

## Verificatie
- [ ] Django API testen met curl (GET/PUT met Bearer token)
- [ ] Web UI testen in browser - items toevoegen, slepen, checken, verwijderen
- [ ] Mac app builden en testen - sync verifiëren met web UI

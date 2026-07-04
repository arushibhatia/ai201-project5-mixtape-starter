# Codebase Map

Here I will map out the organization and the structure of this codebase before attempting to even solve the bugs.

## Organization
### app.py
Flask application factory (create_app). Owns the single `db = SQLAlchemy()` instance that every model/service imports from. Reads DATABASE_URL and SECRET_KEY from the environment, registers the four blueprints (songs, playlists, users, feed) under their url prefixes, and calls db.create_all() on startup. This is also the entry point (python app.py), there's no separate run.py.

### seed_data.py
Populates the dev database with sample users/songs/playlists so there's data to test against. Not imported by app.py itself, it's a standalone script.

### models.py
The models.py file defines several SQLAlchemy tables - User, Tag, Song, ListeningEvent, Rating, Playlist, Notification. These tables each have relatinships to each other, defined by Foreign Keys and db.relationship.

For example, Playlist has a relationship to many Song rows. We see that secondary=playlist_entries denotes that this is a many to many relationship can be seen through the join table called playlist_entries.

There are 3 assocation tables total - friendships, song_tags, and playlist_entires.

### Services
The service layer sits on top of the model layer and applies the business logic layers and sits between the routes (user's entry points) and the data models.

There are several services - Feed Service, Notification Service, Playlist Service, Search Service, and Streak Service.

Each service has various functions that are invoked either directly or indirectly via the route layer.

#### Feed Service
get_friends_listening_now - takes user id and returns a list of dictionaries, each with friend, song, and listened_at keys. There is filtration to make sure only recent listens are included.

get_activity_feed - Returns most recent N listening events across all friends. Takes user_id and limit (N). It returns a list of activity dicts ordered by recent first.

#### Notification Service
create_notification - Takes the user id and the type of notification that that user should receive, along with a body which is the human readable message of the notification. It assembles and returns a notification instance.

add_to_playlist - This takes the playlist_id, song_id, and added_by_user_id and adds a record that a user added a song to a playlist. This also notifies the song's sharer.

rate_song - This saves a user's rating for a song by taking the user_id, song_id, and score (which is a number 1-5). It returns the created or updated Rating instance.

get_notifications - Retrieves the notifications based on user_id and a boolean that indicates whether only unread notifications should be returned.

mark_as_read - Marks notification as read per the notification_id.

#### Playlist Service
create_playlist - Creates a new playlist using the name, user id, and whether the playlist is collaborative. This doesn't actually add any songs but it basically sets up the Playlist instance.

get_playlist_songs - Returns, based on playlist_id, an ordered list (based on the order in which they were added, ascending) of the songs in the playlist.

get_playlist - Based on a playlist_id returns its metadata (excluding the songs). The metadata is returned in a dict.

get_user_playlists - Based on user_id, returns a list of playlist dicts that represent the user's created playlists.

#### Search Service
search_songs - Searches the song by a query, where the query is a string. The query is the title or artist name. It returns all songs where the title or artist contains the query string (case-insensitive), along with their associated tags.

get_song - Retrieves song (and the retrieval is by the song dict) by song id.

#### Streak Service
record_listening_event - Records that a user listened to a song, and updates their streak by using user_id and song_id as input. The result is a ListeningEvent that represents that.

update_listening_streak - Update a user's listening streak based on their last listening date. There are several rules that govern how the streak is calculated.

get_streak - Get the current listening streak for a user by user_id, and the return value is an int representing streak duration.

### Routes
#### Feed
listening_now - calls get_friends_listening_now.

activity - calls get_activity_feed.

#### Playlist
create - calls create_playlist.

get_detail - calls get_playlist.

get_songs - calls get_playlist_songs.

add_song - calls add_to_playlist

#### Songs
search - calls search_songs.

get_song_detail - calls get_song.

rate - calls rate_song.

listen - calls record_listening_event.

#### Users
get_user - calls the db directly to retrieve user based on user id

streak - calls get_streak.

notifications - calls get_notifications.

read_notifications - calls mark_as_read.

Every route follows the same shape: parse request.get_json()/query args, do presence checks on required fields (400 if missing), call exactly one service function, and catch ValueError to turn it into a 4xx JSON error. The one exception is users.get_user, which queries db.session.get(User, user_id) directly instead of going through a service — it's the only route that touches the db import at all.

## Data Flows

### Adding a song to a playlist (triggers a notification)

1. Client sends POST /playlists/<playlist_id>/songs with {song_id, added_by} in the body (routes/playlists.py, add_song).
2. The route only checks that song_id and added_by are present, then calls add_to_playlist(playlist_id, song_id, added_by). Notably this import comes from notification_service, not playlist_service, even though it reads as playlist logic.
3. add_to_playlist (services/notification_service.py) loads the Song, User (adder), and Playlist by id, raising ValueError (→ 400 at the route) if any is missing.
4. If the song isn't already in playlist.songs, it appends it through the playlist.songs relationship (backed by the playlist_entries association table) and commits.
5. Then the notification check: if song.shared_by != added_by_user_id (you didn't add your own shared song), it calls create_notification(user_id=song.shared_by, ...) with a body like "{adder} added your song '{title}' to the playlist '{name}'." So the notification always goes to whoever originally shared the song, not the playlist's creator.
6. create_notification just builds and commits a Notification row — there's no push/email/websocket delivery, "notifying" someone means a row now exists for them.
7. The recipient sees it later via GET /users/<user_id>/notifications (optionally ?unread_only=true → get_notifications), and clears it via POST /users/notifications/<id>/read → mark_as_read.

The interesting part: there's no notification when a song is *shared* in the first place — sharing just creates a Song row with shared_by set. The notification only fires when someone else later acts on that song (adding it to a playlist, or rating it — rate_song is the other notification_service function called from routes/songs.py). That's actually why add_to_playlist and rate_song both live in notification_service.py instead of playlist_service.py/being inline in the route — they're grouped by "this needs to fire a notification as a side effect," not by which resource they're about.

## Patterns

- Routes are thin, services own all business logic, models own serialization (every model has a to_dict(), so nothing hand-serializes a row).
- ValueError is used as the app's "not found / invalid input" signal everywhere. Services never return None for a missing record, they raise ValueError(f"... not found"), and every route has a copy-pasted `except ValueError as e: return jsonify({"error": str(e)}), 4xx` around its one service call. There's no shared error-handling decorator.
- Services are grouped by side effect, not strictly by resource — notification_service.py owning add_to_playlist and rate_song is the clearest example (see data flow above).
- Association tables carry more than the join — playlist_entries stores position, added_by, and added_at, which is how playlist ordering and "who added this" get tracked without a separate model.
- Notifications have no delivery mechanism — "notify" always means "insert a Notification row," and the recipient finds out by polling GET /users/<id>/notifications. There's no websocket/push/email path in the codebase.

## Root Cause Analysis

### Issue #1 — My listening streak keeps resetting

**How I reproduced it:** Ran `pytest tests/test_streaks.py` — `test_streak_increments_on_sunday` fails (`assert 1 == 2`). Confirmed independently by calling `update_listening_streak(user, saturday)` then `update_listening_streak(user, sunday)` with two fixed UTC datetimes (2024-06-15 Saturday → 2024-06-16 Sunday): streak stayed at 1 instead of advancing to 2. Also built a debug endpoint (`services/debug_service.py` + `routes/debugging.py`, gated behind `MIXTAPE_DEBUG_ROUTES=1`) that lets you POST a `date`/`days_ago` and simulate a listen on it, so this is reproducible live via curl on any two real dates, not just in a script. Condition needed: any two consecutive-day listens where the *second* day is a Sunday — every other day-of-week transition increments correctly.

**How I found the root cause:**

**The root cause:**

**Fix and side-effect check:**

### Issue #2 — Friends Listening Now shows people from yesterday

**How I reproduced it:** Created two friended users and a song, then inserted a `ListeningEvent` for the friend timestamped `real_now - 23h30m`. That instant falls on the previous calendar date (e.g. real now `2026-07-04 23:04 UTC` → event at `2026-07-03 23:34 UTC`) but is still inside the 24-hour cutoff. Calling `get_friends_listening_now(user_id)` directly returned that friend/event — confirmed live against the actual system clock, no mocking needed. Condition needed: a friend's listening event that's under 24 hours old by wall-clock time but was logged on the previous calendar date — i.e. any listen from roughly the last 24 hours around a midnight boundary, viewed the next day.

**How I found the root cause:**

**The root cause:**

**Fix and side-effect check:**

### Issue #3 — The same song keeps showing up twice in search

**How I attempted to reproduce it:** Ran `pytest tests/test_search.py` — all 5 tests **pass**, including `test_search_no_duplicates_multi_tag_song`, whose comment literally says "Should be 1, bug causes it to be 3." Reproduced the fixture manually too: created a song with 3 tags inserted directly into the `song_tags` join table (same pattern as the test/seed data), called `search_songs(...)`, got exactly 1 result — not 3. Checked the raw SQL directly against the DB (bypassing the ORM) and confirmed the join genuinely returns 3 physical rows at the SQLite level — but SQLAlchemy 2.0.51's `Query(Song).all()` deduplicates full-entity results by primary key before handing them back, so the fan-out never reaches `search_songs`'s caller. This is a *latent* bug: the underlying defect is real (see root cause below), but it isn't currently observable as the reported symptom in this dependency version, so I couldn't honestly claim to have triggered the visible behavior — only the structural cause that could produce it under a different SQLAlchemy version or query style.

**How I found the root cause:**

**The root cause:**

**Fix and side-effect check:**

### Issue #4 — Notified when a song is added to a playlist but not when it's rated

**How I reproduced it:** Created a sharer and a separate rater, a song owned by the sharer, called `rate_song(rater.id, song.id, 5)`, then checked `get_notifications(sharer.id)` → returned `[]`. Repeating the same setup through `add_to_playlist` instead does produce a notification, which isolates the missing behavior specifically to `rate_song`. Condition needed: any user other than a song's sharer rates that song.

**How I found the root cause:**

**The root cause:**

**Fix and side-effect check:**

### Issue #5 — The last song in a playlist never shows up

**How I reproduced it:** `pytest tests/test_playlists.py` — `test_playlist_returns_all_songs` and `test_playlist_returns_songs_in_order` both fail; a 5-song playlist returns only 4 (`Track 5` missing). Reproduced independently by creating a playlist, inserting 3 `playlist_entries` rows directly at positions 1-3, and calling `get_playlist_songs` — got back only positions 1-2. Condition needed: any playlist with at least one song — a single-song playlist returns an empty list, and an N-song playlist always drops the Nth.

**How I found the root cause:**

**The root cause:**

**Fix and side-effect check:**


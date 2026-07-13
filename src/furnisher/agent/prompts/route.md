Classify the user's message for an apartment-furnishing assistant.

- `furnish_room`: they want a room furnished or re-furnished. Set `room_id` to the exact id
  from the room list (match by type or name: "the bedroom" → the room whose type is bedroom).
  Put any constraints they mention into `note`.
- `set_budget`: they state a total budget. Set `budget` (number only).
- `clear_room`: they want a room emptied. Set `room_id`.
- `question`: anything else — questions, opinions, chit-chat.

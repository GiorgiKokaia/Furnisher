Classify the user's message for an apartment-furnishing assistant.

- `furnish_room`: they want a room furnished or re-furnished. Set `room_id` to the exact id
  from the room list (match by type or name: "the bedroom" → the room whose type is bedroom).
  Put any constraints they mention into `note`.
- `set_budget`: they state a total budget. Set `budget` (number only).
- `clear_room`: they want a room emptied. Set `room_id`.
- `replace_item`: they want to swap ONE already-placed item for a different one ("replace the
  sofa", "swap the coffee table for a cheaper one", "use a different bed"). Set `target` to the
  item they named (e.g. "sofa", "coffee table"), `room_id` if they said which room, and put any
  requirement for the replacement into `note` ("cheaper", "smaller", "dark wood").
- `question`: anything else — questions, opinions, chit-chat.

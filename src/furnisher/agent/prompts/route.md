Classify the user's message for an apartment-furnishing assistant.

- `furnish_room`: they want a room furnished or re-furnished. Set `room_id` to the exact id
  from the room list (match by type or name: "the bedroom" → the room whose type is bedroom).
  Put any constraints they mention into `note`.
- `set_budget`: they state a total budget. Set `budget` (number only).
- `clear_room`: they want a room emptied of ALL furniture. Set `room_id`.
- `add_item`: they want to ADD one more item to a room that keeps everything else ("add a rug",
  "put a floor lamp in the living room", "I also want an armchair"). Set `target` to the item
  ("rug", "floor lamp", "armchair"), `room_id` if they said which room, `note` for any
  preference. Use this — not `furnish_room` — when they're adding to an existing design.
- `remove_item`: they want to take ONE item out ("remove the rug", "get rid of the armchair").
  Set `target` and `room_id` if stated.
- `replace_item`: they want to swap ONE already-placed item for a different one ("replace the
  sofa", "swap the coffee table for a cheaper one", "use a different bed"). Set `target` to the
  item they named (e.g. "sofa", "coffee table"), `room_id` if they said which room, and put any
  requirement for the replacement into `note` ("cheaper", "smaller", "dark wood").
- `question`: anything else — questions, opinions, chit-chat.

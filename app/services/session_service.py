import threading
import time


class ChatSession:
    """Conversation state for a single chat room (may hold multiple members)."""

    def __init__(self, room_id, npc_role, personality, lang, is_rag, success_keyword=None, answer_key=None):
        self.room_id = room_id
        self.npc_role = npc_role
        self.personality = personality
        self.lang = lang
        self.is_rag = is_rag
        self.success_keyword = success_keyword  # LLM-judged story-mode success condition, if any
        self.answer_key = answer_key  # correct-answer content/judging criteria backing success_keyword, if any
        self.members = {}  # sid -> user_name
        self.history = []  # [{"role": "user"|"npc", "sender": str, "content": str}]
        self.created_at = time.time()

    def add_message(self, role, sender, content):
        self.history.append({"role": role, "sender": sender, "content": content})


class SessionService:
    """In-memory registry of chat rooms.

    Rooms live only in process memory: history is lost on restart or across
    multiple worker processes. Fine for a single-process deployment; swap for
    Redis-backed storage if the backend is ever scaled to multiple workers.
    """

    def __init__(self, history_limit=20):
        self._rooms = {}
        self._sid_to_room = {}
        self._lock = threading.Lock()
        self.history_limit = history_limit

    def join(self, sid, room_id, user_name, npc_role, lang, personality, is_rag, success_keyword=None, answer_key=None, opening_line=None):
        with self._lock:
            session = self._rooms.get(room_id)
            if session is None:
                session = ChatSession(room_id, npc_role, personality, lang, is_rag, success_keyword, answer_key)
                self._rooms[room_id] = session
                # Seed the room's history with the NPC's own opening line (e.g. the riddle
                # it just asked in a different, isolated story-mode room) so this fresh
                # session isn't blank — the NPC "remembers" it via the normal history
                # mechanism instead of needing a separate prompt block.
                if opening_line:
                    session.add_message('npc', npc_role, opening_line)
            session.members[sid] = user_name
            self._sid_to_room[sid] = room_id
            return session

    def ensure_room(self, room_id, npc_role, personality='', lang='zh-TW', is_rag=True):
        """Get or create a room's session without any socket membership.

        Used by one-shot flows (e.g. story mode) that ask a question and want
        the reply routed straight back to them, rather than joining/leaving a
        room the way live chat does.
        """
        with self._lock:
            session = self._rooms.get(room_id)
            if session is None:
                session = ChatSession(room_id, npc_role, personality, lang, is_rag)
                self._rooms[room_id] = session
            return session

    def leave(self, sid):
        """Remove sid from whatever room it's in. Returns the room_id it left, or None."""
        with self._lock:
            room_id = self._sid_to_room.pop(sid, None)
            if room_id is None:
                return None
            session = self._rooms.get(room_id)
            if session is not None:
                session.members.pop(sid, None)
                if not session.members:
                    del self._rooms[room_id]
            return room_id

    def get_room(self, room_id):
        with self._lock:
            return self._rooms.get(room_id)

    def get_session_by_sid(self, sid):
        with self._lock:
            room_id = self._sid_to_room.get(sid)
            if room_id is None:
                return None
            return self._rooms.get(room_id)

    def add_message(self, room_id, role, sender, content):
        with self._lock:
            session = self._rooms.get(room_id)
            if session is not None:
                session.add_message(role, sender, content)

    def get_history(self, room_id, exclude_last=False):
        with self._lock:
            session = self._rooms.get(room_id)
            if session is None:
                return []
            history = session.history[:-1] if exclude_last and session.history else session.history
            history = history[-self.history_limit:]
            return list(history)


session_service = SessionService()

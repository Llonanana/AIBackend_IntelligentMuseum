from flask import request
from flask_socketio import join_room, leave_room, emit

from app.services.session_service import session_service
from app.services.npc_service import ask_npc


def register_socket_events(socketio):

    @socketio.on('connect')
    def handle_connect():
        print(f"[socket] client connected: {request.sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        _leave_current_room(request.sid, notify_self=False)

    @socketio.on('join')
    def handle_join(data):
        data = data or {}
        sid = request.sid
        room_id = data.get('room_id')
        npc_role = data.get('npc_role', '博物館導覽員')

        if not room_id:
            emit('error', {'message': 'room_id is required'})
            return

        # Switching rooms (e.g. talking to a different NPC) implicitly leaves the old one.
        _leave_current_room(sid, notify_self=False)

        user_name = data.get('user_name') or f"User_{sid[:6]}"
        lang = data.get('lang', 'zh-TW')
        personality = data.get('personality', '')
        is_rag = data.get('is_rag', True)
        success_keyword = data.get('success_keyword') or None
        answer_key = data.get('answer_key') or None
        opening_line = data.get('opening_line') or None
        hint = data.get('hint') or None
        print(f"[socket] join room_id={room_id} npc_role={npc_role} success_keyword={success_keyword!r} answer_key={answer_key!r} opening_line={opening_line!r} hint={hint!r}")

        join_room(room_id)
        session_service.join(sid, room_id, user_name, npc_role, lang, personality, is_rag, success_keyword, answer_key, opening_line, hint)

        emit('room_joined', {'room_id': room_id})
        emit('system_message', {'message': f'{user_name} 加入了聊天室'}, room=room_id, include_self=False)

    @socketio.on('leave')
    def handle_leave():
        _leave_current_room(request.sid, notify_self=True)

    @socketio.on('get_history')
    def handle_get_history(data=None):
        sid = request.sid
        session = session_service.get_session_by_sid(sid)
        if session is None:
            emit('error', {'message': 'You are not in a room. Send "join" first.'})
            return

        emit('chat_history', {'room_id': session.room_id, 'history': session_service.get_history(session.room_id)})

    @socketio.on('send_chat_message')
    def handle_send_chat_message(data):
        sid = request.sid
        message = (data or {}).get('message', '')
        message = message.strip() if message else ''
        if not message:
            return

        session = session_service.get_session_by_sid(sid)
        if session is None:
            emit('error', {'message': 'You are not in a room. Send "join" first.'})
            return

        room_id = session.room_id
        user_name = session.members.get(sid, 'User')

        session_service.add_message(room_id, 'user', user_name, message)
        emit('user_message', {'user_name': user_name, 'message': message}, room=room_id)
        emit('npc_typing', {}, room=room_id)

        socketio.start_background_task(_generate_npc_reply, socketio, room_id, message)

    @socketio.on('story_prompt')
    def handle_story_prompt(data):
        data = data or {}
        sid = request.sid
        room_id = data.get('room_id')
        npc_role = data.get('npc_role', '博物館導覽員')
        prompts = [p.strip() for p in (data.get('prompts') or []) if (p or '').strip()]

        if not room_id or not prompts:
            emit('error', {'message': 'room_id and prompts are required'})
            return

        socketio.start_background_task(_generate_story_line, socketio, sid, room_id, npc_role, prompts)


def _leave_current_room(sid, notify_self):
    room_id = session_service.leave(sid)
    if room_id is None:
        return
    leave_room(room_id, sid=sid)
    if notify_self:
        emit('room_left', {'room_id': room_id})
    emit('system_message', {'message': '有使用者離開了聊天室'}, room=room_id)


def _generate_npc_reply(socketio, room_id, message):
    session = session_service.get_room(room_id)
    if session is None:
        return

    history = session_service.get_history(room_id, exclude_last=True)

    try:
        result = ask_npc(
            query=message,
            lang=session.lang,
            npc_role=session.npc_role,
            personality=session.personality,
            is_rag=session.is_rag,
            history=history,
            success_keyword=session.success_keyword,
            answer_key=session.answer_key,
            hint=session.hint,
        )
    except Exception as e:
        socketio.emit('error', {'message': f'NPC generation failed: {e}'}, room=room_id)
        return

    response_text = result['response']
    session_service.add_message(room_id, 'npc', session.npc_role, response_text)
    socketio.emit('npc_response', {'npc_role': session.npc_role, 'response': response_text}, room=room_id)


def _generate_story_line(socketio, sid, room_id, npc_role, prompts):
    # No one ever "joins" a story-mode room (StoryPromptManager never sends a "join"
    # event), so the reply goes straight back to the requester's own sid instead of
    # being broadcast to a socket.io room nobody is a member of.
    beat_count = len(prompts)
    # Each prompt is a director-authored line for its own animation beat (see
    # StoryModeManager.RequestDialogueLine); with more than one, they're bundled into a
    # single numbered-task query so one LLM call answers all of them instead of one call
    # per beat. ask_npc/generate_response_with_retrieval only ever see one query string,
    # so the "there are N things to answer" framing lives entirely in this combined text.
    combined_query = prompts[0] if beat_count <= 1 else "\n".join(
        f"任務{i + 1}：{p}" for i, p in enumerate(prompts)
    )

    session_service.ensure_room(room_id, npc_role)
    session_service.add_message(room_id, 'user', 'director', combined_query)
    history = session_service.get_history(room_id, exclude_last=True)

    try:
        result = ask_npc(
            query=combined_query,
            lang='zh-TW',
            npc_role=npc_role,
            personality='',
            is_rag=True,
            history=history,
            beat_count=beat_count,
        )
    except Exception as e:
        socketio.emit('error', {'message': f'Story line generation failed: {e}'}, room=sid)
        return

    response_text = result['response']
    segments = result['segments']
    session_service.add_message(room_id, 'npc', npc_role, response_text)
    socketio.emit('story_response', {'npc_role': npc_role, 'response': response_text, 'segments': segments}, room=sid)

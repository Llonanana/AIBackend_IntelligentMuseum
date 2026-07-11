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

        join_room(room_id)
        session_service.join(sid, room_id, user_name, npc_role, lang, personality, is_rag)

        emit('room_joined', {'room_id': room_id})
        emit('system_message', {'message': f'{user_name} 加入了聊天室'}, room=room_id, include_self=False)

    @socketio.on('leave')
    def handle_leave():
        _leave_current_room(request.sid, notify_self=True)

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
        )
    except Exception as e:
        socketio.emit('error', {'message': f'NPC generation failed: {e}'}, room=room_id)
        return

    response_text = result['response']
    session_service.add_message(room_id, 'npc', session.npc_role, response_text)
    socketio.emit('npc_response', {'npc_role': session.npc_role, 'response': response_text}, room=room_id)

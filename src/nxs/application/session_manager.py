"""
Session Manager - Future Multi-Session Support

PLACEHOLDER FOR FUTURE IMPLEMENTATION

Planned Feature:
-----------------
Support multiple concurrent conversation sessions, allowing users to switch
between different conversations (like browser tabs).

Design Goals:
- Each session has independent AgentLoop with separate message history
- Users can create, switch between, and delete sessions
- Session state can be persisted/restored
- Active session determines which conversation receives user input

Implementation Sketch:
----------------------

from typing import Dict, Optional
from nxs.application.chat import AgentLoop
from nxs.application.claude import Claude
from nxs.domain.protocols import MCPClient
from collections.abc import Mapping


class SessionManager:
    '''Manages multiple conversation sessions.'''

    def __init__(self, llm: Claude, clients: Mapping[str, MCPClient]):
        self.llm = llm
        self.clients = clients
        self.sessions: Dict[str, AgentLoop] = {}
        self.active_session_id: Optional[str] = None

    def create_session(self, session_id: str, callbacks=None) -> AgentLoop:
        '''Create a new conversation session.'''
        if session_id in self.sessions:
            raise ValueError(f"Session '{session_id}' already exists")

        agent_loop = AgentLoop(self.llm, self.clients, callbacks)
        self.sessions[session_id] = agent_loop
        return agent_loop

    def get_session(self, session_id: str) -> Optional[AgentLoop]:
        '''Get existing session by ID.'''
        return self.sessions.get(session_id)

    def get_active_session(self) -> Optional[AgentLoop]:
        '''Get the currently active session.'''
        if self.active_session_id:
            return self.sessions.get(self.active_session_id)
        return None

    def switch_session(self, session_id: str) -> AgentLoop:
        '''Switch to different session.'''
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' does not exist")

        self.active_session_id = session_id
        return self.sessions[session_id]

    def delete_session(self, session_id: str) -> None:
        '''Delete a session and its state.'''
        if session_id in self.sessions:
            del self.sessions[session_id]

        if self.active_session_id == session_id:
            self.active_session_id = None

    def list_sessions(self) -> list[str]:
        '''List all session IDs.'''
        return list(self.sessions.keys())


# TODO: Persistence layer
# class SessionPersistence:
#     def save_session(self, session_id: str, messages: list)
#     def load_session(self, session_id: str) -> list
#     def delete_session(self, session_id: str)


# TODO: UI integration
# - Add session tabs/selector to TUI
# - Keyboard shortcuts for switching (Ctrl+Tab, Ctrl+1-9, etc.)
# - Visual indicator of active session
# - Session rename/label functionality


# TODO: State management
# - Auto-save session state on exit
# - Restore sessions on startup
# - Session max size limits
# - Session cleanup/archival
"""

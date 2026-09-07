import os
import socket
import sys
for key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ[key] = ""
_connect = socket.socket.connect
def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        raise AssertionError("NETWORK BLOCKED DURING REVIEW")
    return _connect(self, address)
socket.socket.connect = connect
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))

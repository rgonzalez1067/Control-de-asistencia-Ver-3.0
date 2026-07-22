"""
Iteration 8 — Kiosk face matching hardening.

Two parts:
  1. Python simulation of the JS matching algorithm in KioskScanPage.jsx
     validates the 3-rule sequence (threshold → margin → consecutive) with
     the exact constants MATCH_THRESHOLD=0.48, MATCH_MARGIN=0.06, REQUIRED_CONSECUTIVE=3.
  2. Backend smoke test on 5 kiosk endpoints still operational.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://asistencia-web-1.preview.emergentagent.com").rstrip("/")
if "REACT_APP_BACKEND_URL" not in os.environ and os.path.exists("/app/frontend/.env"):
    with open("/app/frontend/.env") as _f:
        for _l in _f:
            if _l.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = _l.split("=", 1)[1].strip().rstrip("/")
                break
ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PASSWORD = "admin123"

MATCH_THRESHOLD = 0.48
MATCH_MARGIN = 0.06
REQUIRED_CONSECUTIVE = 3


# ---------------------------------------------------------------------------
# 1. Pure-Python simulation of the JS scan() logic
# ---------------------------------------------------------------------------
class MatchState:
    """Mirrors consecutiveRef.current in the React component."""
    def __init__(self):
        self.user_id = None
        self.count = 0

    def reset(self):
        self.user_id = None
        self.count = 0


def simulate_frame(distances, state):
    """
    Simulates one frame of scan().
    Returns tuple (outcome, status)
      outcome ∈ { "no_face", "weak", "ambiguous", "verifying", "matched" }
    """
    if distances is None:  # no face detected
        state.reset()
        return "no_face", None

    ordered = sorted(distances, key=lambda x: x[1])
    best_uid, best_d = ordered[0]
    second_d = ordered[1][1] if len(ordered) > 1 else None

    # Rule 1: threshold
    if best_d >= MATCH_THRESHOLD:
        state.reset()
        return "weak", None

    # Rule 2: margin between best and second
    if second_d is not None and (second_d - best_d) < MATCH_MARGIN:
        state.reset()
        return "ambiguous", "Rostro ambiguo — acércate un poco o usa PIN"

    # Rule 3: consecutive frames
    if state.user_id == best_uid:
        state.count += 1
    else:
        state.user_id = best_uid
        state.count = 1

    if state.count < REQUIRED_CONSECUTIVE:
        return "verifying", best_uid

    # Match confirmed → reset like the JS code does
    state.reset()
    return "matched", best_uid


class TestMatchingLogic:
    """Reproduces the 3-case unit test requested in the review."""

    def test_case_a_clear_match_confirms_after_3_frames(self):
        state = MatchState()
        distances = [("alice", 0.30), ("bob", 0.60)]
        # frame 1
        out, _ = simulate_frame(distances, state)
        assert out == "verifying" and state.count == 1
        # frame 2
        out, _ = simulate_frame(distances, state)
        assert out == "verifying" and state.count == 2
        # frame 3 → confirmed
        out, uid = simulate_frame(distances, state)
        assert out == "matched"
        assert uid == "alice"
        # After match, state resets so the modal is not re-fired immediately
        assert state.user_id is None and state.count == 0

    def test_case_b_ambiguous_rejects(self):
        state = MatchState()
        distances = [("alice", 0.35), ("bob", 0.38)]
        for _ in range(5):
            out, status = simulate_frame(distances, state)
            assert out == "ambiguous"
            assert status == "Rostro ambiguo — acércate un poco o usa PIN"
            assert state.count == 0  # never accumulates on ambiguity

    def test_case_c_weak_rejects(self):
        state = MatchState()
        distances = [("alice", 0.55), ("bob", 0.90)]
        for _ in range(5):
            out, _ = simulate_frame(distances, state)
            assert out == "weak"
            assert state.count == 0

    def test_case_boundary_threshold_equal_is_rejected(self):
        """0.48 exactly should NOT match (>=)."""
        state = MatchState()
        out, _ = simulate_frame([("alice", 0.48), ("bob", 0.90)], state)
        assert out == "weak"

    def test_case_boundary_margin_exact_is_ambiguous(self):
        """Margin 0.06 exactly (>=? No: strict < means 0.06 is NOT ambiguous)."""
        state = MatchState()
        # diff = 0.42-0.36 = 0.06 → NOT < 0.06 → passes margin
        out, _ = simulate_frame([("alice", 0.36), ("bob", 0.42)], state)
        assert out == "verifying"

    def test_case_no_face_resets_counter(self):
        state = MatchState()
        # Frame 1: verifying
        simulate_frame([("alice", 0.30), ("bob", 0.60)], state)
        simulate_frame([("alice", 0.30), ("bob", 0.60)], state)
        assert state.count == 2
        # No face → reset
        simulate_frame(None, state)
        assert state.count == 0 and state.user_id is None

    def test_case_switching_user_resets_counter(self):
        state = MatchState()
        simulate_frame([("alice", 0.30), ("bob", 0.60)], state)
        simulate_frame([("alice", 0.30), ("bob", 0.60)], state)
        assert state.user_id == "alice" and state.count == 2
        # Suddenly frame favours bob → counter must restart at 1 for bob
        simulate_frame([("bob", 0.28), ("alice", 0.60)], state)
        assert state.user_id == "bob" and state.count == 1

    def test_case_ambiguous_between_verifying_frames_resets(self):
        """After 2 verifying frames, one ambiguous frame must reset — user must restart."""
        state = MatchState()
        clear = [("alice", 0.30), ("bob", 0.60)]
        ambig = [("alice", 0.35), ("bob", 0.38)]
        simulate_frame(clear, state)
        simulate_frame(clear, state)
        assert state.count == 2
        out, _ = simulate_frame(ambig, state)
        assert out == "ambiguous"
        assert state.count == 0

    def test_original_bug_scenario_similar_faces_never_matches(self):
        """The reported bug: two similar employees (small margin) — algorithm must
        NEVER confirm a match, no matter how many frames pass."""
        state = MatchState()
        distances = [("empA", 0.34), ("empB", 0.37)]  # margin 0.03 < 0.06
        outcomes = [simulate_frame(distances, state)[0] for _ in range(50)]
        assert all(o == "ambiguous" for o in outcomes)
        assert state.count == 0


# ---------------------------------------------------------------------------
# 2. Backend kiosk endpoints regression (5 endpoints smoke test)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def api():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestKioskEndpointsRegression:
    def test_roster_public(self, api):
        r = api.get(f"{BASE_URL}/api/kiosk/roster")
        assert r.status_code == 200
        roster = r.json()
        assert isinstance(roster, list)
        # Ensure onboarded users have descriptor arrays (needed by the new matcher)
        onboarded = [u for u in roster if u.get("face_descriptor")]
        for u in onboarded[:3]:
            assert isinstance(u["face_descriptor"], list)
            assert len(u["face_descriptor"]) > 0
            assert isinstance(u["selfie_base64"], str)

    def test_next_type_endpoint(self, api, auth_headers):
        me = api.get(f"{BASE_URL}/api/auth/me", headers=auth_headers).json()
        uid = me["user_id"]
        r = api.get(f"{BASE_URL}/api/kiosk/next-type/{uid}")
        assert r.status_code == 200
        d = r.json()
        assert d.get("next_type") in ("in", "out")

    def test_kiosk_attendance_check_auto(self, api, auth_headers):
        """POST /api/kiosk/attendance/check with type='auto' still works."""
        # create a throwaway user to avoid polluting admin history
        email = f"TEST_iter8_kiosk_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST Iter8 Kiosk",
            "role": "employee", "password": "pw12345",
        })
        assert rc.status_code == 200
        uid = rc.json()["user_id"]
        try:
            r = api.post(f"{BASE_URL}/api/kiosk/attendance/check",
                         json={"user_id": uid, "type": "auto"})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["type"] in ("in", "out")
            assert d["user_id"] == uid
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)

    def test_reenroll_face_requires_pin(self, api, auth_headers):
        """POST /api/kiosk/reenroll-face without PIN → 401 (regression from iter7)."""
        email = f"TEST_iter8_re_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST Iter8 Reenroll",
            "role": "employee", "password": "pw12345",
        })
        assert rc.status_code == 200
        uid = rc.json()["user_id"]
        try:
            # user has no PIN → any submission should be rejected
            r = requests.post(
                f"{BASE_URL}/api/kiosk/reenroll-face",
                data={"user_id": uid, "pin": "1234",
                      "selfie_base64": "data:image/jpeg;base64,AAA"},
            )
            assert r.status_code == 401
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)

    def test_kiosk_unlock_admin(self, api):
        r = api.post(f"{BASE_URL}/api/kiosk/unlock",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert r.json()["ok"] is True

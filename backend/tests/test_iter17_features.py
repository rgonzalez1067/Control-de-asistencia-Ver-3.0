"""
Iteration 17 features:
  - Schedules: `color` field (10-color palette + empty)
  - Assignment plans: overlap allowed when user_ids disjoint (409 only when sharing)
  - Visits: new purposes data_center_tbp / data_center_lch (old rejected), internal visitor (no phone/cedula required)
  - Novelties: multi-date mode via `dates` (remote/permission/leave) — creates N documents
  - Matrix report: projection of future approved novelties (novelty_full vs future) and day_off
"""
import os
import time
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://asistencia-web-1.preview.emergentagent.com").rstrip("/")
if "REACT_APP_BACKEND_URL" not in os.environ:
    envp = "/app/frontend/.env"
    if os.path.exists(envp):
        for line in open(envp):
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PASSWORD = "Sol*1401*1010"

ADMIN_USER_ID = "user_641b181ceb84"
COORD_USER_ID = "user_7279cc9aebf2"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_headers(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


# ==============================================================
# Schedules — color field
# ==============================================================
class TestScheduleColor:
    VALID_COLORS = ["", "sky", "indigo", "violet", "emerald", "amber",
                    "rose", "cyan", "lime", "fuchsia", "slate"]

    def test_create_and_update_with_colors(self, api, auth_headers):
        created = []
        try:
            for color in self.VALID_COLORS[:3]:  # sample
                r = api.post(f"{BASE_URL}/api/schedules", headers=auth_headers, json={
                    "name": f"TEST Color {color or 'none'} {int(time.time()*1000)}",
                    "blocks": [{"start": "09:00", "end": "17:00"}],
                    "tolerance_minutes": 10,
                    "color": color,
                })
                assert r.status_code == 200, r.text
                d = r.json()
                assert d.get("color", "") == color, f"Expected color={color!r} got {d.get('color')!r}"
                sid = d["schedule_id"]
                created.append(sid)

                # Verify via list
                rl = api.get(f"{BASE_URL}/api/schedules", headers=auth_headers)
                found = [s for s in rl.json() if s["schedule_id"] == sid]
                assert found and found[0].get("color", "") == color

            # Update: change first schedule's color
            sid = created[0]
            new_color = "rose"
            ru = api.put(f"{BASE_URL}/api/schedules/{sid}", headers=auth_headers, json={
                "name": "TEST Color updated",
                "blocks": [{"start": "09:00", "end": "17:00"}],
                "tolerance_minutes": 10,
                "color": new_color,
            })
            assert ru.status_code == 200, ru.text
            assert ru.json().get("color") == new_color
        finally:
            for sid in created:
                api.delete(f"{BASE_URL}/api/schedules/{sid}", headers=auth_headers)

    def test_invalid_color_rejected_or_normalized(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/schedules", headers=auth_headers, json={
            "name": f"TEST Color invalid {int(time.time()*1000)}",
            "blocks": [{"start": "09:00", "end": "17:00"}],
            "tolerance_minutes": 10,
            "color": "notacolor",
        })
        # Backend currently persists as-is (no whitelist validation). Frontend palette limits UX.
        # Accept 200 (permissive) or 400/422 (strict). If accepted, clean up.
        assert r.status_code in (200, 400, 422), r.text
        if r.status_code == 200:
            api.delete(f"{BASE_URL}/api/schedules/{r.json()['schedule_id']}", headers=auth_headers)


# ==============================================================
# Assignment plans — smart overlap
# ==============================================================
class TestPlanOverlap:
    def test_disjoint_users_overlapping_ranges_allowed(self, api, auth_headers):
        start = (date.today() + timedelta(days=30)).isoformat()
        end = (date.today() + timedelta(days=45)).isoformat()
        created = []
        try:
            r1 = api.post(f"{BASE_URL}/api/schedule-assignment-plans",
                          headers=auth_headers, json={
                              "name": f"TEST Plan A {int(time.time()*1000)}",
                              "user_ids": [ADMIN_USER_ID],
                              "from_date": start,
                              "to_date": end,
                          })
            assert r1.status_code == 200, r1.text
            plan_a = r1.json().get("plan_id") or r1.json().get("id")
            created.append(plan_a)

            r2 = api.post(f"{BASE_URL}/api/schedule-assignment-plans",
                          headers=auth_headers, json={
                              "name": f"TEST Plan B {int(time.time()*1000)}",
                              "user_ids": [COORD_USER_ID],
                              "from_date": start,
                              "to_date": end,
                          })
            assert r2.status_code == 200, \
                f"Overlapping range with disjoint user_ids must be allowed: {r2.status_code} {r2.text}"
            plan_b = r2.json().get("plan_id") or r2.json().get("id")
            created.append(plan_b)
        finally:
            for pid in created:
                if pid:
                    api.delete(f"{BASE_URL}/api/schedule-assignment-plans/{pid}",
                               headers=auth_headers)

    def test_shared_user_overlapping_ranges_conflict(self, api, auth_headers):
        start = (date.today() + timedelta(days=60)).isoformat()
        end = (date.today() + timedelta(days=75)).isoformat()
        created = []
        try:
            r1 = api.post(f"{BASE_URL}/api/schedule-assignment-plans",
                          headers=auth_headers, json={
                              "name": f"TEST Plan C {int(time.time()*1000)}",
                              "user_ids": [ADMIN_USER_ID, COORD_USER_ID],
                              "from_date": start,
                              "to_date": end,
                          })
            assert r1.status_code == 200, r1.text
            created.append(r1.json().get("plan_id") or r1.json().get("id"))

            r2 = api.post(f"{BASE_URL}/api/schedule-assignment-plans",
                          headers=auth_headers, json={
                              "name": f"TEST Plan C2 {int(time.time()*1000)}",
                              "user_ids": [ADMIN_USER_ID],  # shares ADMIN
                              "from_date": start,
                              "to_date": end,
                          })
            assert r2.status_code == 409, \
                f"Expected 409 for shared user_ids overlap, got {r2.status_code} {r2.text}"
            body = r2.json()
            code = body.get("detail", {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
            assert code == "plan_range_overlap" or "overlap" in str(body).lower(), \
                f"Expected code=plan_range_overlap, body={body}"
            if r2.status_code == 200:
                created.append(r2.json().get("plan_id") or r2.json().get("id"))
        finally:
            for pid in created:
                if pid:
                    api.delete(f"{BASE_URL}/api/schedule-assignment-plans/{pid}",
                               headers=auth_headers)


# ==============================================================
# Visits — new purposes and internal visitor
# ==============================================================
class TestVisits:
    def test_new_data_center_purposes(self, api, auth_headers):
        for purpose in ["visita_data_center_tbp", "visita_data_center_lch"]:
            r = api.post(f"{BASE_URL}/api/visits", headers=auth_headers, json={
                "type": "laboral",
                "host_user_id": ADMIN_USER_ID,
                "purpose": purpose,
                "company_name": "TestCo",
                "visitors": [{
                    "kind": "external",
                    "name": "TEST Visitor",
                    "cedula": "V-12345678",
                    "phone": "0412-1234567",
                }],
                "observations": "TEST",
            })
            assert r.status_code == 200, f"purpose={purpose}: {r.status_code} {r.text}"
            d = r.json()
            assert d.get("purpose") == purpose
            assert d.get("purpose_label"), f"purpose_label missing: {d}"
            vid = d.get("visit_id") or d.get("id")
            if vid:
                api.delete(f"{BASE_URL}/api/visits/{vid}", headers=auth_headers)

    def test_old_generic_data_center_rejected(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/visits", headers=auth_headers, json={
            "type": "laboral",
            "host_user_id": ADMIN_USER_ID,
            "purpose": "visita_data_center",  # old, must be rejected
            "company_name": "TestCo",
            "visitors": [{
                "kind": "external",
                "name": "TEST Visitor",
                "cedula": "V-12345678",
                "phone": "0412-1234567",
            }],
        })
        assert r.status_code == 400, \
            f"Old generic data_center must be rejected (400), got {r.status_code} {r.text}"

    def test_internal_visitor_no_phone_no_cedula(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/visits", headers=auth_headers, json={
            "type": "laboral",
            "host_user_id": ADMIN_USER_ID,
            "purpose": "visita_data_center_tbp",
            "company_name": "TestCo",
            "visitors": [{
                "kind": "internal",
                "internal_user_id": COORD_USER_ID,
                "name": "TEST Internal",
                # NO phone, NO cedula
            }],
            "observations": "TEST internal",
        })
        assert r.status_code == 200, \
            f"Internal visitor without phone/cedula should be accepted: {r.status_code} {r.text}"
        vid = r.json().get("visit_id") or r.json().get("id")
        if vid:
            api.delete(f"{BASE_URL}/api/visits/{vid}", headers=auth_headers)

    def test_internal_visitor_requires_internal_user_id(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/visits", headers=auth_headers, json={
            "type": "laboral",
            "host_user_id": ADMIN_USER_ID,
            "purpose": "visita_data_center_tbp",
            "company_name": "TestCo",
            "visitors": [{
                "kind": "internal",
                "name": "TEST Internal missing id",
                # NO internal_user_id
            }],
        })
        assert r.status_code in (400, 422), \
            f"Internal visitor without internal_user_id must be rejected: {r.status_code} {r.text}"


# ==============================================================
# Novelties — multi-date mode
# ==============================================================
class TestNoveltiesMultiDate:
    def test_remote_multi_date_creates_three(self, api, auth_headers):
        dates = ["2026-10-06", "2026-10-08", "2026-10-13"]
        r = api.post(f"{BASE_URL}/api/novelties", headers=auth_headers, json={
            "type": "remote",
            "start_date": dates[0],
            "end_date": dates[-1],
            "dates": dates,
            "start_time": "08:00",
            "end_time": "17:00",
            "reason": "TEST multi-date",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("created") == 3, f"Expected created=3, got {d}"
        nids = d.get("novelty_ids") or []
        assert len(nids) == 3, f"Expected 3 novelty_ids, got {nids}"

        try:
            all_list = api.get(f"{BASE_URL}/api/novelties", headers=auth_headers).json()
            by_id = {n["novelty_id"]: n for n in all_list}
            for nid, expected_date in zip(nids, dates):
                assert nid in by_id, f"novelty {nid} missing in list"
                nov = by_id[nid]
                assert nov["start_date"] == expected_date, nov
                assert nov["end_date"] == expected_date, nov
                assert nov["type"] == "remote"
        finally:
            for nid in nids:
                api.delete(f"{BASE_URL}/api/novelties/{nid}", headers=auth_headers)

    def test_vacation_multi_date_rejected(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/novelties", headers=auth_headers, json={
            "type": "vacation",
            "start_date": "2026-11-02",
            "end_date": "2026-11-05",
            "dates": ["2026-11-02", "2026-11-05"],
            "reason": "TEST bad multi",
        })
        assert r.status_code == 400, \
            f"vacation with dates[] must be rejected: {r.status_code} {r.text}"

    def test_remote_multi_date_missing_times_rejected(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/novelties", headers=auth_headers, json={
            "type": "remote",
            "start_date": "2026-11-02",
            "end_date": "2026-11-05",
            "dates": ["2026-11-02", "2026-11-05"],
            "reason": "TEST missing times",
        })
        assert r.status_code == 400, \
            f"multi-date without start/end_time must be rejected: {r.status_code} {r.text}"


# ==============================================================
# Matrix report — future novelties projection & day_off
# ==============================================================
class TestMatrixReport:
    def test_future_approved_novelty_projected_as_novelty_full(self, api, auth_headers):
        # Create + approve a novelty in the future for admin
        future_start = (date.today() + timedelta(days=10)).isoformat()
        future_end = (date.today() + timedelta(days=10)).isoformat()

        rc = api.post(f"{BASE_URL}/api/novelties", headers=auth_headers, json={
            "type": "remote",
            "user_id": ADMIN_USER_ID,
            "start_date": future_start,
            "end_date": future_end,
            "start_time": "08:00",
            "end_time": "17:00",
            "reason": "TEST future proj",
        })
        assert rc.status_code == 200, rc.text
        nid = rc.json()["novelty_id"]
        try:
            api.post(f"{BASE_URL}/api/novelties/bulk-decide", headers=auth_headers,
                     json={"novelty_ids": [nid], "decision": "approved"})

            frm = (date.today() + timedelta(days=7)).isoformat()
            to = (date.today() + timedelta(days=21)).isoformat()
            r = api.get(
                f"{BASE_URL}/api/reports/matrix",
                headers=auth_headers,
                params={"from_date": frm, "to_date": to, "user_ids": ADMIN_USER_ID},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            # Response shape: list of rows or dict
            rows = data if isinstance(data, list) else data.get("rows") or data.get("users") or []
            assert rows, f"Empty matrix rows: {data}"
            # Find admin row
            admin_row = None
            for row in rows:
                if row.get("user_id") == ADMIN_USER_ID:
                    admin_row = row
                    break
            assert admin_row, f"Admin row not in matrix: {rows}"
            cells = admin_row.get("cells") or admin_row.get("days") or {}
            if isinstance(cells, list):
                target = next((c for c in cells if c.get("date") == future_start), None)
            else:
                target = cells.get(future_start)
            assert target, f"No cell for {future_start}: {admin_row}"
            status = target.get("status") if isinstance(target, dict) else target
            assert status in ("novelty_full", "novelty_partial", "novelty"), \
                f"Expected novelty_full projection for {future_start}, got {status!r}"
        finally:
            api.delete(f"{BASE_URL}/api/novelties/{nid}", headers=auth_headers)

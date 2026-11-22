"""Browser checks for P1-08 using the real control-plane test client."""

import os

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")


base_url = "http://ariba.test"


@pytest.fixture
def portal_page(client, seeded_fixtures):
    def forward(route):
        request = route.request
        response = client.request(
            request.method,
            request.url.removeprefix(base_url),
            content=request.post_data_buffer,
            headers=request.headers,
        )
        route.fulfill(
            status=response.status_code,
            headers=dict(response.headers),
            body=response.content,
        )

    try:
        with playwright_api.sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(executable_path=os.environ.get("PAM_TEST_CHROMIUM"))
            except Exception as exc:
                pytest.skip(f"Playwright chromium launch not available: {exc}")
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.route(base_url + "/**", forward)
            page.goto(base_url + "/portal")
            yield page
            browser.close()
    except Exception as exc:
        pytest.skip(f"Playwright driver not available: {exc}")


def sign_in(page, user):
    page.get_by_label("Synthetic email").fill(user.email)
    page.get_by_label("Synthetic subject").fill(user.idp_subject)
    page.get_by_role("button", name="Sign in", exact=True).click()


def test_browser_sign_in_and_scoped_catalog(portal_page, seeded_fixtures):
    page = portal_page
    expect = playwright_api.expect
    pending = []
    page.route("**/api/v1/assets", lambda route: pending.append(route), times=1)

    sign_in(page, seeded_fixtures["alice"])
    expect(page.get_by_role("status")).to_have_text("Loading permitted assets…")
    assert len(pending) == 1
    pending[0].fallback()

    expect(page.get_by_role("heading", name="payment-db-01.lab")).to_be_visible()
    expect(page.get_by_text("root · Ticket required")).to_be_visible()
    expect(page.get_by_text("analytics-db-01.lab")).to_have_count(0)
    assert page.evaluate("localStorage.length + sessionStorage.length") == 0

    page.get_by_role("button", name="Sign out", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("Signed out.")
    expect(page.get_by_text("payment-db-01.lab")).to_have_count(0)


def test_browser_handles_empty_and_denied(portal_page, seeded_fixtures, db_session):
    page = portal_page
    expect = playwright_api.expect

    sign_in(page, seeded_fixtures["disabled"])
    expect(page.get_by_role("status")).to_contain_text("Lab sign-in denied.")

    alice = seeded_fixtures["alice"]
    alice.role_assignments.clear()
    db_session.commit()
    sign_in(page, alice)
    expect(page.get_by_role("status")).to_have_text("No assets are assigned to your identity.")

    page.route("**/api/v1/assets", lambda route: route.fulfill(status=403), times=1)
    page.get_by_role("button", name="Refresh catalog").click()
    expect(page.get_by_role("status")).to_contain_text("does not have permission")

    page.route("**/api/v1/assets", lambda route: route.fulfill(status=401), times=1)
    page.get_by_role("button", name="Refresh catalog").click()
    expect(page.get_by_role("status")).to_contain_text("session expired")
    expect(page.get_by_role("heading", name="Lab sign-in")).to_be_visible()

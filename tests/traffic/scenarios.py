"""
Test traffic scenarios — each function configures a Selenium WebDriver
with specific characteristics to trigger different OFM detection rules.

Usage:
    # Run a single scenario:
    python scenarios.py vanilla --test-domain http://frontend:3000

    # Run all scenarios:
    python scenarios.py --all --test-domain http://frontend:3000 --repeat 3
"""

import os
import time
import argparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


# ── Helpers ──


def _make_driver(hub_url, extra_args=None, window_size=None, mobile_emulation=None):
    """Create a Chrome WebDriver connected to a Selenium Grid hub."""
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")

    if extra_args:
        for arg in extra_args:
            opts.add_argument(arg)

    if window_size:
        opts.add_argument(f"--window-size={window_size[0]},{window_size[1]}")

    if mobile_emulation:
        opts.add_experimental_option("mobileEmulation", mobile_emulation)

    driver = webdriver.Remote(
        command_executor=hub_url,
        options=opts,
    )

    if window_size:
        driver.set_window_size(window_size[0], window_size[1])

    return driver


def _visit_and_wait(driver, url, dwell=8):
    """Navigate to a page and wait for fingerprint collection + heartbeat."""
    driver.get(url)
    time.sleep(dwell)


# ── Scenario registry ──

SCENARIOS = {}


def scenario(name, description):
    """Decorator to register a scenario."""
    def decorator(fn):
        fn.scenario_name = name
        fn.scenario_desc = description
        SCENARIOS[name] = fn
        return fn
    return decorator


# ── Scenarios ──


@scenario("vanilla", "Normal Chrome browser — baseline (should score low)")
def vanilla(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, window_size=(1920, 1080))
    try:
        _visit_and_wait(driver, demo_url, dwell)
        _visit_and_wait(driver, demo_url + "?page=2", dwell // 2)
    finally:
        driver.quit()


@scenario("headless", "Headless Chrome — triggers webdriver + headless detections")
def headless(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, extra_args=["--headless=new"], window_size=(1920, 1080))
    try:
        _visit_and_wait(driver, demo_url, dwell)
    finally:
        driver.quit()


@scenario("tiny_screen", "Very small screen (320x240) — triggers screen anomalies")
def tiny_screen(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, window_size=(320, 240))
    try:
        _visit_and_wait(driver, demo_url, dwell)
    finally:
        driver.quit()


@scenario("zero_screen", "Zero-size headless window — triggers headlessChromeScreenResolution")
def zero_screen(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, extra_args=["--headless=new", "--window-size=0,0"])
    try:
        _visit_and_wait(driver, demo_url, dwell)
    finally:
        driver.quit()


@scenario("mobile", "Mobile device emulation — Galaxy S5")
def mobile(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, mobile_emulation={
        "deviceMetrics": {"width": 360, "height": 640, "pixelRatio": 3.0},
        "userAgent": (
            "Mozilla/5.0 (Linux; Android 10; SM-G950F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Mobile Safari/537.36"
        ),
    })
    try:
        _visit_and_wait(driver, demo_url, dwell)
    finally:
        driver.quit()


@scenario("bot_ua", "Bot-like User-Agent — triggers hasBotUserAgent")
def bot_ua(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, extra_args=[
        "--user-agent=Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ], window_size=(1920, 1080))
    try:
        _visit_and_wait(driver, demo_url, dwell)
    finally:
        driver.quit()


@scenario("utc_timezone", "Headless + forced UTC — triggers hasUTCTimezone")
def utc_timezone(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, extra_args=["--headless=new"], window_size=(1920, 1080))
    try:
        driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": "UTC"})
        _visit_and_wait(driver, demo_url, dwell)
    finally:
        driver.quit()


@scenario("swiftshader", "SwiftShader GPU — triggers hasSwiftshaderRenderer")
def swiftshader(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, extra_args=["--headless=new", "--use-gl=swiftshader"],
                          window_size=(1920, 1080))
    try:
        _visit_and_wait(driver, demo_url, dwell)
    finally:
        driver.quit()


@scenario("multi_page", "Normal browser visiting 5 pages — rich URL history")
def multi_page(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, window_size=(1440, 900))
    try:
        for page in ["", "?p=products", "?p=checkout", "?p=account", "?p=help"]:
            _visit_and_wait(driver, demo_url + page, max(2, dwell // 5))
    finally:
        driver.quit()


@scenario("rapid", "Rapid repeated visits — high frequency fingerprinting")
def rapid(demo_url, hub_url, dwell):
    driver = _make_driver(hub_url, window_size=(1366, 768))
    try:
        for i in range(5):
            driver.get(demo_url + f"?visit={i}")
            time.sleep(1)
        time.sleep(dwell)
    finally:
        driver.quit()


# ── Runner ──


def run(names, test_domain, hub_url, repeat, dwell):
    demo_url = f"{test_domain}/demo.html"

    for name in names:
        sc = SCENARIOS[name]
        for i in range(repeat):
            tag = f"[{name}] ({i+1}/{repeat})" if repeat > 1 else f"[{name}]"
            print(f"{tag} {sc.scenario_desc}")
            try:
                sc(demo_url, hub_url, dwell)
                print(f"{tag} ✓ done")
            except Exception as e:
                print(f"{tag} ✗ failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OFM test traffic generator")
    parser.add_argument("scenario", nargs="?", help="Scenario name to run")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument(
        "--test-domain",
        dest="test_domain",
        default=os.environ.get("TEST_DOMAIN", "http://frontend:3000"),
        help="Base domain where demo.html is served (e.g. http://frontend:3000)",
    )
    parser.add_argument(
        "--backend",
        dest="test_domain",
        default=argparse.SUPPRESS,
        help="Deprecated alias for --test-domain",
    )
    parser.add_argument("--hub", default=os.environ.get("SELENIUM_HUB", "http://selenium-hub:4444/wd/hub"))
    parser.add_argument("--repeat", type=int, default=int(os.environ.get("REPEAT", "1")))
    parser.add_argument("--dwell", type=int, default=int(os.environ.get("DWELL", "10")))
    args = parser.parse_args()

    if args.all:
        names = list(SCENARIOS.keys())
    elif args.scenario:
        if args.scenario not in SCENARIOS:
            print(f"Unknown scenario: {args.scenario}")
            print(f"Available: {', '.join(SCENARIOS.keys())}")
            raise SystemExit(1)
        names = [args.scenario]
    else:
        # If SCENARIO env var is set, use it (for docker-compose)
        env_scenario = os.environ.get("SCENARIO")
        if env_scenario:
            names = [env_scenario]
        else:
            print("Specify a scenario name or --all")
            print(f"Available: {', '.join(SCENARIOS.keys())}")
            raise SystemExit(1)

    run(names, args.test_domain, args.hub, args.repeat, args.dwell)

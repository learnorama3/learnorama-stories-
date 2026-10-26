"""Post today's Learnorama Instagram Story via the Instagram API.

Env vars:
  IG_USER_ID       Instagram account ID
  IG_ACCESS_TOKEN  access token with instagram_business_content_publish
  STORY_DATE       optional YYYY-MM-DD override (for testing)
  DRY_RUN=1        print what would be posted, post nothing
  TEST_ONLY=1      create and process the container, but do not publish
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
GRAPH = "https://graph.instagram.com/v21.0"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
LOG = ROOT / "posted.json"


def call(path, params, post=True):
    data = urllib.parse.urlencode(params)
    if post:
        req = urllib.request.Request(f"{GRAPH}/{path}", data=data.encode(), method="POST")
    else:
        req = urllib.request.Request(f"{GRAPH}/{path}?{data}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Instagram API error {e.code}: {e.read().decode()}")


def main():
    now = dt.datetime.now(IST)
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        # GitHub often starts timed runs hours late. A run before 4 am still
        # belongs to the previous evening; runs between 4 am and 7 pm wait.
        if now.hour < 4:
            now -= dt.timedelta(days=1)
        elif now.hour < 19:
            print(f"Too early in the day ({now:%H:%M} IST) for a timed run; waiting for the evening.")
            return
    today = os.environ.get("STORY_DATE") or now.date().isoformat()
    rows = {r["date"]: r for r in csv.DictReader(open(ROOT / "schedule.csv"))}
    row = rows.get(today)
    if not row:
        print(f"No story scheduled for {today}.")
        return
    log = json.loads(LOG.read_text()) if LOG.exists() else {}
    if today in log:
        print(f"Day {row['day']} already posted ({log[today]['media_id']}).")
        return

    print(f"Day {row['day']} ({today}, {row['media']}): {row['url']}")
    if os.environ.get("DRY_RUN") == "1":
        return

    user, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    key = "video_url" if row["media"] == "video" else "image_url"
    container = call(f"{user}/media", {
        key: row["url"], "media_type": "STORIES", "access_token": token})["id"]
    for _ in range(60):
        s = call(container, {"fields": "status_code", "access_token": token}, post=False).get("status_code")
        print(f"  container {container}: {s}")
        if s == "FINISHED":
            break
        if s == "ERROR":
            sys.exit(f"Instagram could not process {row['url']}")
        time.sleep(10)
    else:
        sys.exit("Instagram did not finish processing in 10 minutes.")
    if os.environ.get("TEST_ONLY") == "1":
        print("Test only: not publishing.")
        return

    media = call(f"{user}/media_publish", {
        "creation_id": container, "access_token": token})["id"]
    log[today] = {"day": int(row["day"]), "media_id": media,
                  "posted_at": dt.datetime.now(IST).isoformat(timespec="seconds")}
    LOG.write_text(json.dumps(log, indent=2) + "\n")
    print(f"Posted Day {row['day']} as media {media}.")


if __name__ == "__main__":
    main()

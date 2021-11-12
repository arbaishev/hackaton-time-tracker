import datetime
import logging
from time import sleep

import requests

from dotenv import dotenv_values

config = dotenv_values(".env")
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
)


def round_up_duration(minutes, base=30):
    return minutes + (base - minutes) % base


def get_list_unresolved_issues():
    path = "/api/issues"
    query = {
        "for": config["ASSIGNEE"],
        "Board " + config["BOARD"]: "{Current sprint}",
        "State": "Unresolved",
    }
    params = {
        "fields": "id,customFields(name,value(id,name))",
        "query": " ".join([key + ":" + value for key, value in query.items()]),
    }
    headers = {
        "Authorization": "Bearer " + config["API_TOKEN"],
        "Accept": "application/json",
    }
    response = requests.get(config["HOST"] + path, params=params, headers=headers)
    logger.info("Successful fetched issues states")

    return {
        issue["id"]: {
            "state": custom_field["value"]["name"],
            "timestamp": str(get_issue_activities(issue["id"])),
        }
        for issue in response.json()
        for custom_field in issue["customFields"]
        if custom_field["$type"] == "StateIssueCustomField"
    }


def get_issue_activities(issue):
    path = "/api/issues/" + issue + "/activities"
    params = {
        "fields": "timestamp,author(name),field(id,name)",
        "categories": "CustomFieldCategory",
    }
    headers = {
        "Authorization": "Bearer " + config["API_TOKEN"],
        "Accept": "application/json",
    }
    response = requests.get(config["HOST"] + path, params=params, headers=headers)
    logger.info(f"Successful fetched activities for issue: {issue}")

    return "".join(
        map(
            str,
            [
                activity["timestamp"]
                for activity in response.json()
                if activity["field"]["id"] == config["CUSTOM_FIELD_STATE_ID"]
            ][-1:],
        )
    )


def add_worktime(issue, duration):
    path = "/api/issues/" + issue + "/timeTracking/workItems"
    body = {
        "date": datetime.datetime.now().timestamp() * 1000,
        "author": {"id": config["USER_ID"]},
        "duration": {"minutes": round_up_duration(duration)},
        "type": {"id": config["WORKTIME_BACKEND_ID"]},
    }

    headers = {
        "Authorization": "Bearer " + config["API_TOKEN"],
        "Content-Type": "application/json",
    }

    try:
        requests.post(config["HOST"] + path, headers=headers, json=body)
        logger.info(f"Successfull added worktime for issue {issue}")
    except requests.RequestException:
        logger.error("Не удалось выполнить запрос", exc_info=True)


def compare_states(old, new):
    diff_keys = [key for key in old if old[key] != new[key]]

    for key in diff_keys:
        if new[key]["state"] == "To Verify" and old[key]["state"] == "In Progress":
            timedelta = round(
                (
                    datetime.datetime.fromtimestamp(
                        round(int(new[key]["timestamp"]) / 1000)
                    )
                    - datetime.datetime.fromtimestamp(
                        round(int(old[key]["timestamp"]) / 1000)
                    )
                ).total_seconds()
                / 60
            )

            add_worktime(issue=key, duration=timedelta)
            return True
    return False


if __name__ == "__main__":
    old_states = get_list_unresolved_issues()

    while True:
        sleep(600)
        new_states = get_list_unresolved_issues()
        updated = compare_states(old_states, new_states)
        if updated:
            old_states = new_states

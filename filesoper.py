"""
Module for writing/reading files.
"""
import json
import os
import logging
logger = logging.getLogger(__name__)


def write_json(json_data, write_file):
    """
    Saves all info about goods by their appliers.
    "user1_id": {
                url1: {
                        "title":str,
                        "price":int,
                        "isPromoForCardPrice": bool,
                        "promoDate": str,
                        "repeatNotif": bool
                        },
                url2: {...}
    "user2_id": {...}
    """
    with open(write_file, "w") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)


def read_json(file_path):
    """
    Read a json file.
    return: Dictionary or empty dictionary.
    """
    if os.path.isfile(file_path):
        with open(file_path, "r") as f:
            try:
                return json.load(f, object_hook=jsonKeys2int)
            except json.decoder.JSONDecodeError:
                logger.error(f"Can't decode file {file_path}")
    return {}


def jsonKeys2int(some_dict):
    """
    Json can't use integers as keys, so user_id writes as a string.
    This function converts every string key in dict to an integer(if it can).
    """
    if isinstance(some_dict, dict):
        try:
            return {int(k): v for k, v in some_dict.items()}
        except ValueError:
            pass
    return some_dict

import json
import logging
import sys
import time
from kiteconnect import KiteConnect

CREDENTIALS_FILE = "./creds.json"

logger = logging.getLogger("root")

def load_credentials(file_path=CREDENTIALS_FILE):
    try:
        with open(file_path, "r") as file:
            data = json.load(file)
            logger.debug("Loaded credentials from %s", file_path)
            return data
    except FileNotFoundError:
        logger.error("Credentials file not found: %s", file_path)
        raise
    except json.JSONDecodeError as e:
        logger.error("Error parsing credentials file: %s", e)
        raise

def save_credentials(credentials, file_path=CREDENTIALS_FILE):
    try:
        with open(file_path, "w") as file:
            json.dump(credentials, file, indent=4)
            logger.debug("Saved credentials to %s", file_path)
    except Exception as e:
        logger.error("Failed to save credentials to %s: %s", file_path, e)
        raise

def load_access_token():
    credentials = load_credentials()
    token = credentials.get("accessToken")
    if token:
        logger.debug("Access token loaded from credentials")
    else:
        logger.info("No access token found in credentials")
    return token

def save_access_token(access_token):
    credentials = load_credentials()
    credentials["accessToken"] = access_token  
    save_credentials(credentials)
    logger.info("Access token saved successfully to creds.json")

def kite_login():

    is_token_valid = False

    try:
        while not is_token_valid:
            credentials = load_credentials()
            api_key = credentials["apiKey"]
            api_secret = credentials["secret"]

            kite = KiteConnect(api_key=api_key)
            access_token = load_access_token()

            if not access_token:
                print("No stored access token found. Fetching a new one...")

            if access_token:
                kite.set_access_token(access_token)
                try:
                    profile = kite.profile()  # Verify token validity
                    is_token_valid = True
                    print(f"Logged in as {profile['user_name']}")
                except Exception:
                    print("Access token invalid, Waiting for Token to set from FE...")
            else:
                print("Login failed. Please check credentials and try again.")

            time.sleep(5)
            
        return kite

    except Exception as e:
        print(f"Error during Kite login: {e}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    try:
        kite = kite_login()
        try:
            positions = kite.positions()
            logger.info("Current positions fetched successfully")
            print(json.dumps(positions, indent=4))
        except Exception as e:
            logger.error("Error fetching positions: %s", e)
    except Exception as e:
        logger.error("Kite login failed: %s", e)
        sys.exit(1)

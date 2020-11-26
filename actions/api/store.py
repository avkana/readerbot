import json
import logging
from typing import Dict, Text, Any, List
from tinydb import TinyDB, Query

logger = logging.getLogger(__name__)
logging.getLogger("").handlers = []
logging.basicConfig(format="%(message)s", level=logging.DEBUG)

# TinyDB docs: https://tinydb.readthedocs.io/en/stable/usage.html#updating-data

class Store(object):
  def __init__(self):
    userfile = "users.json"
    self.db = TinyDB(userfile)

  def user_by_email(self, email: Text):
    User = Query()
    try:
      user = self.db.search(User.email == email)
    except:
      user = None
    return user

  def user_by_sender_id(self, channel: Text, sender: Text):
    User = Query()
    try:
      user = self.db.search(User['shell'] == sender)
    except:
      user = None
    return user

  def insert_user(self, user):
    self.db.insert(user)

  def update_user(self, user):
    self.db.update(user)

db = Store()
user = db.user_by_sender_id("shell", "greg")

logger.debug(f"user: {user}")
if not user:
  logger.debug("no users")
  user = {
    "firstName": "Greg",
    "email": "greg@udon.org",
    "shell": "greg",
    "slack": "abc"
  }
  db.insert_user(user)

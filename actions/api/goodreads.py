import os
import logging
from betterreads import client
#from betterreads.client import GoodreadsClient
from typing import Dict, Text, Any, List

logger = logging.getLogger(__name__)
logging.getLogger("").handlers = []
logging.basicConfig(format="%(message)s", level=logging.DEBUG)

class GoodreadsAPI(object):
  """Class to connect to the Algolia API"""

  def __init__(self):
      self.API_KEY = os.getenv('API_KEY')
      self.API_SECRET = os.getenv('API_SECRET')
      self.ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
      self.ACCESS_TOKEN_SECRET = os.getenv('ACCESS_TOKEN_SECRET')
      if not self.API_KEY or not self.API_SECRET:
        logging.error("API key and secret not provided")

      self.gc = client.GoodreadsClient(self.API_KEY, self.API_SECRET)
      self.user_authenticated = False

  def authenticate(self):
    try:
      self.gc.authenticate(self.ACCESS_TOKEN, self.ACCESS_TOKEN_SECRET)
      self.user_authenticated = True
      self.user = self.gc.user()
      self.user_id = self.user.gid
      self.user_name = user.user_name
      logging.debug(f"user.gid: {user.gid}, user_name: {user.user_name}")
    except:
      logging.error("User authentication failed")

# Client Calls
  def find_author(self, name):
    author = self.gc.find_author(name)
    return name

  def search_books(self, value, search_field="all"):
    books = self.gc.search_books(q=value, search_field=search_field)
    #books = self.gc.search_books(q="Snow Crash", search_field="title")
    #books = self.gc.search_books(q="Neal Stephenson", search_field="author")
    #books = self.gc.search_books(q="Snow Crash", search_field="title")
    #books = self.gc.search_books(q="Daniel Mallory Ortberg", search_field="author")
    #books = self.gc.search_books(q=value)
    #books = self.gc.search_books(q=value, search_field="title", page=20)
    #books = self.gc.search_books(q=value, search_field=search_field, page=20)
    return books

# User Calls
  def user(self):
    if not self.user_authenticated:
      self.authenticate()
    if self.user_authenticated:
      self.user = self.gc.user()
      self.user_id = self.user.gid
      self.user_name = user.user_name
      logging.debug(f"user.gid: {user.gid}, user_name: {user.user_name}")
      return self.user
    else:
      logging.error("User not authenticated")

  def shelves(self):
    if not self.user_authenticated:
      self.authenticate()
    if self.user_authenticated:
      shelves = self.user.shelves()
      logging.debug(f"shelves: {shelves}")
      return shelves
    else:
      logging.error("User not authenticated")

gr = GoodreadsAPI()
books = gr.search_books("think on these things", "title")
#books = gr.search_books("snow crash", page=20, search_field="all")
gr.authenticate()
shelves = gr.shelves()
logger.debug(f"user shelves: {shelves}")

import os
import logging
from betterreads import client

logger = logging.getLogger(__name__)
logging.getLogger("").handlers = []
logging.basicConfig(format="%(message)s", level=logging.DEBUG)

API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('ACCESS_TOKEN_SECRET')
if not API_KEY or not API_SECRET:
  logging.error("API key and secret not provided")
  exit(1)
gc = client.GoodreadsClient(API_KEY, API_SECRET)
gc.authenticate(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
if not ACCESS_TOKEN:
  # this is the first time we've gotten their token, store this in profile
  logger.debug(f"access_token: {gc.session.access_token}, access_token_secret: {gc.session.access_token_secret}")
  # also get and store their user info the first time

user = gc.user()
logging.debug(f"user.gid: {user.gid}, user_name: {user.user_name}")

shelves = user.shelves
logging.debug(f"shelves: {shelves}")
#book = gc.book(1)
#logging.debug(f"book: {book}")

class GoodreadsAPI(object):
  """Class to connect to the Algolia API"""

  def __init__(self, url: Text):
      self.url = url
      API_KEY = os.getenv('API_KEY')
      API_SECRET = os.getenv('API_SECRET')
      ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
      ACCESS_TOKEN_SECRET = os.getenv('ACCESS_TOKEN_SECRET')
      if not API_KEY or not API_SECRET:
        logging.error("API key and secret not provided")

      gc = client.GoodreadsClient(API_KEY, API_SECRET)
      gc.authenticate(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

      self.user = gc.user()
      self.user_id = user.gid
      self.user_name = user.user_name
      logging.debug(f"user.gid: {user.gid}, user_name: {user.user_name}")

  @staticmethod
  def get_discourse_links(topics: Optional[List[Dict[Text, Any]]], index: int):
    forum = None
    if topics:
      doc_url = f"https://forum.rasa.com/t/{topics[index].get('slug')}/{str(topics[index].get('id'))}"
      forum = f"- [{topics[index].get('title')}]({doc_url})"
    return forum

  def shelves(self):
    shelves = self.user.shelves
    logging.debug(f"shelves: {shelves}")
    return shelves

# -*- coding: utf-8 -*-
from dataclasses import dataclass, field, asdict
from urllib3 import PoolManager, make_headers
from datetime import datetime, timedelta
from urllib.parse import urlencode
from dacite import from_dict
from threading import RLock
from itertools import chain
from io import BytesIO
from PIL import Image
import certifi
import time
import json
import io


@dataclass(frozen=True)
class JsonFrozen:
    @property
    def json(self):
        return json.dumps(asdict(self))


@dataclass(frozen=False)
class JsonLiquid:
    @property
    def json(self):
        return json.dumps(asdict(self))


@dataclass(frozen=True, order=True)
class File(JsonFrozen):
    width: int
    height: int
    url: str | None
    ext: str = field(default="")
    size: int = field(default=0)
    md5: str = field(default="")
    has: bool = field(default=False, repr=False)

    @property
    def link(self):
        return self.url if self.url else f'https://static1.e621.net/data/{self.md5[slice(0, 2)]}/{self.md5[slice(2, 4)]}/{self.md5}.{self.ext}' if self.md5 and self.ext else None


@dataclass(frozen=True, order=True)
class Score(JsonFrozen):
    up: int
    down: int
    total: int


@dataclass(frozen=True, order=True)
class Tag(JsonFrozen):
    id: int
    name: str
    post_count: int
    related_tags: list
    related_tags_updated_at: str
    category: int
    is_locked: bool
    created_at: str
    updated_at: str

    @property
    def category_name(self):
        categories = {0: "General", 1: "Artist", 3: "Copyright", 4: "Character", 5: "Species", 6: "Invalid", 7: "Meta",
                      8: "Lore"}
        return categories[self.category] if self.category in categories else "Unknown"


@dataclass(frozen=True, order=True)
class TagAlias(JsonFrozen):
    id: int
    status: str
    antecedent_name: str
    consequent_name: str
    post_count: int
    reason: str
    creator_id: int
    approver_id: int
    created_at: str
    updated_at: str
    forum_post_id: int
    forum_topic_id: int


@dataclass(frozen=True, order=True)
class Tags(JsonFrozen):
    general: list = field(default_factory=list)
    species: list = field(default_factory=list)
    character: list = field(default_factory=list)
    copyright: list = field(default_factory=list)
    artist: list = field(default_factory=list)
    invalid: list = field(default_factory=list)
    lore: list = field(default_factory=list)
    meta: list = field(default_factory=list)

    @property
    def all(self):
        return list(
            chain(self.general, self.species, self.character, self.copyright, self.artist, self.invalid, self.lore,
                  self.meta))


@dataclass(frozen=True, order=True)
class Flags(JsonFrozen):
    pending: bool
    flagged: bool
    note_locked: bool
    status_locked: bool
    rating_locked: bool
    deleted: bool


@dataclass(frozen=True, order=True)
class Relationships(JsonFrozen):
    parent_id: int | None
    has_children: bool
    has_active_children: bool
    children: list


@dataclass(frozen=True, order=True)
class Post(JsonFrozen):
    id: int
    created_at: str
    updated_at: str
    file: File
    preview: File
    sample: File
    score: Score
    tags: Tags
    locked_tags: list
    change_seq: int
    flags: Flags
    rating: str
    fav_count: int
    sources: list
    pools: list
    relationships: Relationships
    approver_id: int | None
    uploader_id: int
    description: str
    comment_count: int
    is_favorited: bool
    has_notes: bool
    duration: int | float | None

    @property
    def link(self):
        return f'https://e621.net/posts/{self.id}'

    def download(self) -> io.IOBase:
        if not self.file.link:
            raise ValueError("File Doesn't Exist")
        dl = PoolManager().request('GET', self.file.link)
        if dl.status != 200:
            raise ValueError(dl.status)
        byte = BytesIO()
        byte.name = self.file.url.split('/')[-1]
        byte.write(dl.data)
        byte.seek(0)
        return byte

    def open(self) -> Image:
        if not self.file.link:
            raise ValueError("File Doesn't Exist")
        dl = PoolManager().request('GET', self.file.url)
        if dl.status != 200:
            raise ValueError(dl.status)
        byte = BytesIO()
        byte.name = self.file.url.split('/')[-1]
        byte.write(dl.data)
        byte.seek(0)
        return Image.open(byte)


@dataclass(order=True)
class List(JsonLiquid):
    posts: list[Post]


@dataclass(order=True)
class Pool(JsonLiquid):
    id: int
    name: str
    created_at: str
    updated_at: str | None
    creator_id: int
    description: str
    is_active: bool
    category: str
    is_deleted: bool
    post_ids: list = field(repr=False)
    creator_name: str
    post_count: int
    posts: list[Post] = field(default_factory=list)


@dataclass(frozen=True, order=True)
class Wiki(JsonFrozen):
    id: int
    created_at: str | None
    updated_at: str | None
    title: str | None
    body: str | None
    creator_id: int | None
    is_locked: bool
    updater_id: int | None
    is_deleted: bool
    other_names: list
    creator_name: str | None
    category_name: int


@dataclass()
class E621Error(Exception):
    success: bool
    reason: str | None = field(default=None)
    code: int | None = field(default=None)
    message: str = field(default="")

    def __str__(self):
        return f'{self.__repr__()}'


class ESix:
    _instance = None
    _lock = RLock()

    def __new__(cls, username, api_key):
        if (e621 := cls._instance) is None:
            e621 = cls._instance = super().__new__(cls)
            e621.__init(username, api_key)
        return e621

    def __init(self, username, api_key):
        self.username = username
        self.api_key = api_key
        self.header = make_headers(
            user_agent=f'e621/2.1/{username} by TinyZorro/admin@tinyfox.dev',
            basic_auth=f'{username}:{api_key}')
        self.pool_manager = PoolManager(20, self.header, cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
        self.last_search = datetime.fromtimestamp(0)

    def api_limiter(self):
        with self._lock:
            while self.last_search + timedelta(0, 0.5) > datetime.now(self.last_search.tzinfo):
                time.sleep(0.01)
            self.last_search = datetime.now()

    def post(self, post_id: int):
        self.api_limiter()
        r = self.pool_manager.request('GET', f'https://e621.net/posts/{post_id}.json')
        post = json.loads(r.data.decode('utf-8'))
        if r.status != 200:
            raise E621Error(**post)
        return from_dict(Post, post['post'])

    def search(self, tags: list, limit: int = 160, page: int = 1, safe: bool = False, blacklist=None, score: int = -10):
        if blacklist is None:
            blacklist = list()
        url = 'https://e621.net/' if not safe else 'https://e926.net/'
        posts = []
        while limit > 0:
            self.api_limiter()
            params = {"tags": ' '.join(tags), "limit": limit, "page": page}
            r = self.pool_manager.request('GET', f'{url}posts.json?{urlencode(params)}')
            if r.status != 200:
                raise E621Error(**json.loads(r.data.decode('utf-8')))
            posts += json.loads(r.data.decode('utf-8'))['posts']
            limit -= 320
            page += 1
        search_list = from_dict(List, {"posts": posts})
        for post in list(search_list.posts):
            if any(item in blacklist for item in post.tags.all):
                search_list.posts.remove(post)
            if post.score.total <= score:
                search_list.posts.remove(post)
        return search_list

    def get_pool_images(self, pool: Pool):
        r = self.search([f'pool:{pool.id}'], limit=1280, score=-5000)
        posts = []
        for post in pool.post_ids:
            for p in r.posts:
                if p.flags.deleted:
                    continue
                if p.id == post:
                    posts.append(p)
        return from_dict(List, {"posts": posts})

    def pool(self, pool_id: int):
        encode = urlencode({'commit': 'search', 'search[id]': pool_id})
        r = self.pool_manager.request('GET', f'https://e621.net/pools.json/?{encode}')
        if r.status != 200:
            raise E621Error(**json.loads(r.data.decode('utf-8')))
        pool = from_dict(Pool, json.loads(r.data.decode('utf-8'))[0])
        pool.posts = self.get_pool_images(pool).posts
        return pool

    def pool_search(self, query: str):
        self.api_limiter()
        encode = urlencode({'commit': 'search', 'search[name_matches]': query})
        r = self.pool_manager.request('GET', f'https://e621.net/pools.json/?{encode}')
        if r.status != 200:
            raise E621Error(**json.loads(r.data.decode('utf-8')))
        return [from_dict(Pool, x) for x in json.loads(r.data.decode('utf-8'))]

    def wiki(self, query: str | int):
        self.api_limiter()
        if not query:
            raise E621Error(False, "No Query Provided")
        r = self.pool_manager.request('GET', f'https://e621.net/wiki_pages/{query}.json')
        if r.status != 200:
            raise E621Error(**json.loads(r.data.decode('utf-8')))
        return from_dict(Wiki, json.loads(r.data.decode('utf-8')))

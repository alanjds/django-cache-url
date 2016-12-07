# -*- coding: utf-8 -*-
import os
import re

try:
    import urllib.parse as urlparse
except ImportError:  # python 2
    import urlparse


# Register cache schemes in URLs.
urlparse.uses_netloc.append('db')
urlparse.uses_netloc.append('dummy')
urlparse.uses_netloc.append('file')
urlparse.uses_netloc.append('locmem')
urlparse.uses_netloc.append('uwsgicache')
urlparse.uses_netloc.append('memcached')
urlparse.uses_netloc.append('djangopylibmc')
urlparse.uses_netloc.append('pymemcached')
urlparse.uses_netloc.append('redis')
urlparse.uses_netloc.append('hiredis')

DEFAULT_ENV = 'CACHE_URL'

BACKENDS = {
    'db': 'django.core.cache.backends.db.DatabaseCache',
    'dummy': 'django.core.cache.backends.dummy.DummyCache',
    'file': 'django.core.cache.backends.filebased.FileBasedCache',
    'locmem': 'django.core.cache.backends.locmem.LocMemCache',
    'uwsgicache': 'uwsgicache.UWSGICache',
    'memcached': 'django.core.cache.backends.memcached.PyLibMCCache',
    'djangopylibmc': 'django_pylibmc.memcached.PyLibMCCache',
    'pymemcached': 'django.core.cache.backends.memcached.MemcachedCache',
    'redis': 'django_redis.cache.RedisCache',
    'hiredis': 'django_redis.cache.RedisCache',
}


def config(env=DEFAULT_ENV, default='locmem://'):
    """Returns configured CACHES dictionary from CACHE_URL"""
    config = {}

    s = os.environ.get(env, default)

    if s:
        config = parse(s)

    return config


def parse(url):
    """Parses a cache URL."""
    config = {}

    original_url = url
    url = urlparse.urlparse(url)
    # Handle python 2.6 broken url parsing
    path, query = url.path, url.query
    if '?' in path and query == '':
        path, query = path.split('?', 1)

    cache_args = dict([(key.upper(), ';'.join(val)) for key, val in
                       urlparse.parse_qs(query).items()])

    # Update with environment configuration.
    backend = BACKENDS.get(url.scheme)
    if not backend:
        raise Exception('Unknown backend: "{0}"'.format(url.scheme))

    config['BACKEND'] = BACKENDS[url.scheme]

    redis_options = {}
    if url.scheme == 'hiredis':
        redis_options['PARSER_CLASS'] = 'redis.connection.HiredisParser'

    # Handle multiple locations (hosts or sockets)
    config['LOCATION'] = []

    raw_locations = original_url.split(',')

    if url.scheme:
        for i, raw_location in enumerate(raw_locations):
            if not raw_location.startswith(url.scheme):
                raw_locations[i] = url.scheme + '://' + raw_location

    for raw_location in raw_locations:
        location_url = urlparse.urlparse(raw_location)

        # Handle python 2.6 broken url parsing
        path, query = location_url.path, location_url.query
        if '?' in path and query == '':
            path, query = path.split('?', 1)

        # File based
        if not location_url.netloc:
            if location_url.scheme in ('memcached', 'pymemcached', 'djangopylibmc'):
                config['LOCATION'].append('unix:' + path)

            elif location_url.scheme in ('redis', 'hiredis'):
                match = re.match(r'.+?(?P<db>\d+)', path)
                if match:
                    db = match.group('db')
                    path = path[:path.rfind('/')]
                else:
                    db = '0'
                config['LOCATION'].append('unix:%s:%s' % (path, db))
            else:
                config['LOCATION'].append(path)

        # URL based
        else:
            config['LOCATION'].extend(location_url.netloc.split(','))

            if location_url.scheme in ('redis', 'hiredis'):
                if location_url.password:
                    redis_options['PASSWORD'] = location_url.password
                # Specifying the database is optional, use db 0 if not specified.
                db = path[1:] or '0'
                config['LOCATION'][-1] = "redis://%s:%s/%s" % (
                    location_url.hostname,
                    location_url.port,
                    db
                )

    # Single location may be set not as a list
    if len(config['LOCATION']) == 1 and isinstance(config['LOCATION'], list):
        config['LOCATION'] = config['LOCATION'][0]

    # Memcache likes it in one line.
    elif url.scheme in ('memcached', 'pymemcached', 'djangopylibmc'):
        config['LOCATION'] = ';'.join(config['LOCATION'])

    if redis_options:
        config.setdefault('OPTIONS', {}).update(redis_options)

    if url.scheme == 'uwsgicache':
        config['LOCATION'] = config.get('LOCATION', 'default') or 'default'

    # Pop special options from cache_args
    # https://docs.djangoproject.com/en/1.10/topics/cache/#cache-arguments
    options = {}
    for key in ['MAX_ENTRIES', 'CULL_FREQUENCY']:
        val = cache_args.pop(key, None)
        if val is not None:
            options[key] = int(val)
    if options:
        config.setdefault('OPTIONS', {}).update(options)

    config.update(cache_args)

    return config

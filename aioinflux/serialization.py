import re
import time
import warnings
from collections import defaultdict
from functools import reduce
from itertools import chain
from typing import Dict, Mapping, Union

from . import np, pd

if pd is None:
    import ciso8601


# Special characters documentation:
# https://docs.influxdata.com/influxdb/v1.4/write_protocols/line_protocol_reference/#special-characters
# Although not in the official docs, new line characters are removed in order to avoid issues.
key_escape = str.maketrans({'\\': '\\\\', ',': r'\,', ' ': r'\ ', '=': r'\=', '\n': ''})
tag_escape = str.maketrans({'\\': '\\\\', ',': r'\,', ' ': r'\ ', '=': r'\=', '\n': ''})
str_escape = str.maketrans({'\\': '\\\\', '"': r'\"', '\n': ''})
measurement_escape = str.maketrans({'\\': '\\\\', ',': r'\,', ' ': r'\ ', '\n': ''})


def escape(string, escape_pattern):
    """Assistant function for string escaping"""
    try:
        return string.translate(escape_pattern)
    except AttributeError:
        warnings.warn("Non-string-like data passed. "
                      "Attempting to convert to 'str'.")
        return str(string).translate(tag_escape)


def parse_data(data, measurement=None, tag_columns=None, **extra_tags):
    """Converts input data into line protocol format"""
    if isinstance(data, bytes):
        return data
    elif isinstance(data, str):
        return data.encode('utf-8')
    elif pd is not None and isinstance(data, pd.DataFrame):
        if measurement is None:
            raise ValueError("Missing 'measurement'")
        return parse_df(data, measurement, tag_columns, **extra_tags)
    elif isinstance(data, dict):
        return make_line(data, measurement, **extra_tags).encode('utf-8')
    elif hasattr(data, '__iter__'):
        return b'\n'.join([parse_data(i, measurement, tag_columns, **extra_tags) for i in data])
    else:
        raise ValueError('Invalid input', data)


def make_line(point: Mapping, measurement=None, **extra_tags) -> str:
    """Converts dictionary-like data into a single line protocol line (point)"""
    tags = _parse_tags(point, extra_tags)
    if tags:
        return '{},{} {} {}'.format(
            _parse_measurement(point, measurement), tags,
            _parse_fields(point), _parse_timestamp(point))
    return '{} {} {}'.format(
        _parse_measurement(point, measurement), _parse_fields(point),
        _parse_timestamp(point)
    )


def _parse_measurement(point, measurement):
    try:
        return escape(point['measurement'], measurement_escape)
    except KeyError:
        if measurement is None:
            raise ValueError("'measurement' missing")
        return escape(measurement, measurement_escape)


def _parse_tags(point, extra_tags):
    output = []
    try:
        for k, v in {**point['tags'], **extra_tags}.items():
            k = escape(k, key_escape)
            v = escape(v, tag_escape)
            if not v:
                continue  # ignore blank/null string tags
            output.append('{}={}'.format(k, v))
    except KeyError:
        pass
    if output:
        return ','.join(output)
    else:
        return ''


def _parse_timestamp(point):
    if 'time' not in point:
        return ''
    dt = point['time']
    if pd is not None:
        return pd.Timestamp(dt).value
    if isinstance(dt, (str, bytes)):
        dt = ciso8601.parse_datetime(dt)
        if not dt:
            raise ValueError('Invalid datetime string')
    if not dt.tzinfo:
        # Assume tz-naive input to be in UTC, not local time
        return int(dt.timestamp() - time.timezone) * 10 ** 9 + dt.microsecond * 1000
    return int(dt.timestamp()) * 10 ** 9 + dt.microsecond * 1000


def _parse_fields(point):
    """Field values can be floats, integers, strings, or Booleans."""
    output = []
    for k, v in point['fields'].items():
        k = escape(k, key_escape)
        if isinstance(v, bool):
            output.append('{}={}'.format(k, v))
        elif isinstance(v, int):
            output.append('{}={}i'.format(k, v))
        elif isinstance(v, str):
            output.append('{}="{}"'.format(k, v.translate(str_escape)))
        elif v is None:
            # Empty values
            continue
        else:
            # Floats
            output.append('{}={}'.format(k, v))
    return ','.join(output)


DataFrameType = None if pd is None else Union[bool, pd.DataFrame, Dict[str, pd.DataFrame]]


def make_df(resp, tag_cache=None) -> DataFrameType:
    """Makes list of DataFrames from a response object"""

    def maker(series) -> pd.DataFrame:
        df = pd.DataFrame(series['values'], columns=series['columns'])
        if 'time' not in df.columns:
            return df
        df = df.set_index(pd.to_datetime(df['time'])).drop('time', axis=1)
        df.index = df.index.tz_localize('UTC')
        df.index.name = None
        if 'tags' in series:
            for k, v in series['tags'].items():
                df[k] = v
        if 'name' in series:
            df.name = series['name']
        return df

    def drop_zero_index(df):
        if isinstance(df.index, pd.DatetimeIndex):
            if all(i.value == 0 for i in df.index):
                df.reset_index(drop=True, inplace=True)

    # Parsing
    df_list = [((series['name'], tuple(series.get('tags', {}).items())), maker(series))
               for statement in resp['results'] if 'series' in statement
               for series in statement['series']]

    # Concatenation
    d = defaultdict(list)
    for k, df in sorted(df_list, key=lambda x: x[0]):
        d[k].append(df)
    dfs = {k: pd.concat(v, axis=0) for k, v in d.items()}

    # Post-processing
    for (name, _), df in dfs.items():
        drop_zero_index(df)
        if not tag_cache or name not in tag_cache:
            continue
        for col, tags in tag_cache[name].items():
            if col not in df.columns:
                continue
            # Change tag columns dtype from object to categorical
            dtype = pd.api.types.CategoricalDtype(categories=tags)
            df[col] = df[col].astype(dtype=dtype)

    # Return
    if len(dfs) == 1:
        return dfs[list(dfs.keys())[0]]
    return dfs


def itertuples(df):
    """Custom implementation of ``DataFrame.itertuples`` that
    returns plain tuples instead of namedtuples. About 50% faster.
    """
    cols = [df.iloc[:, k] for k in range(len(df.columns))]
    return zip(df.index, *cols)


def make_replacements(df):
    obj_cols = {k for k, v in dict(df.dtypes).items() if v is np.dtype('O')}
    other_cols = set(df.columns) - obj_cols
    obj_nans = ('{}="nan"'.format(k) for k in obj_cols)
    other_nans = ('{}=nan'.format(k) for k in other_cols)
    replacements = [
        ('|'.join(chain(obj_nans, other_nans)), ''),
        (',{2,}', ','),
        ('|'.join([', ,', ', ', ' ,']), ' '),
    ]
    return replacements


def parse_df(df, measurement, tag_columns=None, **extra_tags):
    """Converts a Pandas DataFrame into line protocol format"""

    # Pre-processing
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError('DataFrame index is not DatetimeIndex')
    tag_columns = set(tag_columns or [])
    tag_columns.update(k for k, v in dict(df.dtypes).items()
                       if isinstance(v, pd.api.types.CategoricalDtype))
    isnull = df.isnull().any(axis=1)

    # Make parser function
    tags = []
    fields = []
    for k, v in extra_tags.items():
        tags.append(('{}={{}}'.format(k), '"{}"'.format(escape(v, key_escape))))
    for i, (k, v) in enumerate(df.dtypes.items()):
        k = k.translate(key_escape)
        if k in tag_columns:
            tags.append(('{}={{}}'.format(k), 'p[{}]'.format(i + 1)))
        elif issubclass(v.type, np.integer):
            fields.append(('{}={{}}i'.format(k), 'p[{}]'.format(i + 1)))
        elif issubclass(v.type, (np.float, np.bool_)):
            fields.append(('{}={{}}'.format(k), 'p[{}]'.format(i + 1)))
        else:
            # String escaping is skipped for performance reasons
            # Strings containing double-quotes can cause strange write errors
            # and should be sanitized by the user.
            # e.g., df[k] = df[k].astype('str').str.translate(str_escape)
            fields.append(('{}="{{}}"'.format(k), 'p[{}]'.format(i + 1)))
    fmt_0 = '{}{}{}'.format(measurement, "," if tags else "", ','.join((t[0] for t in tags)))
    fmt_1 = '{}'.format(','.join((f[0] for f in fields)))

    tags_val = ','.join((t[1] for t in tags))
    fields_val = ','.join((f[1] for f in fields))
    f = "lambda p: '{} {} {{}}'.format({}{}{}{} p[0].value)".format(
        fmt_0, fmt_1, tags_val, "," if tags else "", fields_val, "," if fields else "")
    f = eval(f)

    # Map/concat
    if isnull.any():
        lp = map(f, itertuples(df[~isnull]))
        rep = make_replacements(df)
        lp_nan = (reduce(lambda a, b: re.sub(*b, a), rep, f(p))
                  for p in itertuples(df[isnull]))
        return '\n'.join(chain(lp, lp_nan)).encode('utf-8')
    else:
        return '\n'.join(map(f, itertuples(df))).encode('utf-8')

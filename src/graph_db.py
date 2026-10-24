"""A small layer over the official Neo4j Python driver.

The first edition used py2neo, which its maintainers have declared end of life. This module
keeps the three calls the code relies on (`graph.run(query, **params).data()`,
`graph.evaluate(query)` and `graph.create(Node(...))`) on top of the `neo4j` driver.
"""

import datetime

import numpy as np
from neo4j import GraphDatabase, NotificationMinimumSeverity


def _plain(value):
    """Convert NumPy and pandas values to types the driver can send."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


class Result(list):
    """Records of one query, as dictionaries."""

    def data(self):
        return list(self)


class Node(dict):
    """A node to create: one label and its properties."""

    def __init__(self, label, **properties):
        super().__init__(properties)
        self.label = label


class Graph:
    def __init__(self, uri, auth, database=None):
        # Server notifications at WARNING and above (deprecations, for example); the INFO ones are
        # query-planning hints that would print a line for each node the graph step creates
        self.driver = GraphDatabase.driver(uri, auth=auth, notifications_min_severity=NotificationMinimumSeverity.WARNING)
        self.driver.verify_connectivity()
        self.database = database

    def run(self, query, parameters=None, **kwargs):
        params = _plain({**(parameters or {}), **kwargs})
        records, _, _ = self.driver.execute_query(query, parameters_=params, database_=self.database)
        return Result(record.data() for record in records)

    def evaluate(self, query, parameters=None, **kwargs):
        """The first value of the first record, or None."""
        records = self.run(query, parameters, **kwargs)
        return next(iter(records[0].values()), None) if records else None

    def create(self, node):
        self.run(f"CREATE (n:`{node.label}` $properties)", properties=dict(node))

    def close(self):
        self.driver.close()

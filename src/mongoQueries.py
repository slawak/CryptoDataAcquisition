import json
import uuid
import logging
import threading
import traceback
import ast
import itertools
import collections
import datetime


import pymongo

def data_quality(client):
    database = client["MarketData"]
    collection = database["ResultMarketData"]

    # Created with Studio 3T, the IDE for MongoDB - https://studio3t.com/

    pipeline = [
        {
            u"$match": {
                u"request_timestamp": {
                    u"$gt": (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(),
                    u"$lt": (datetime.datetime.now()).isoformat()
                }
            }
        }, 
        {
            u"$group": {
                u"_id": {
                    u"lib": u"$lib",
                    u"exchange": u"$exchange",
                    u"call": u"$call",
                    u"args": u"$args"
                },
                u"lib": {
                    u"$first": u"$lib"
                },
                u"exchange": {
                    u"$first": u"$exchange"
                },
                u"call": {
                    u"$first": u"$call"
                },
                u"args": {
                    u"$first": u"$args"
                },
                u"request_timestamp_max": {
                    u"$max": u"$request_timestamp"
                },
                u"request_timestamp_min": {
                    u"$min": u"$request_timestamp"
                },
                u"count": {
                    u"$sum": 1.0
                },
                u"countError": {
                    u"$sum": {
                        u"$cond": [
                            {
                                u"$eq": [
                                    u"$status",
                                    u"error"
                                ]
                            },
                            1.0,
                            0.0
                        ]
                    }
                },
                u"countWarning": {
                    u"$sum": {
                        u"$cond": [
                            {
                                u"$eq": [
                                    u"$status",
                                    u"warning"
                                ]
                            },
                            1.0,
                            0.0
                        ]
                    }
                }
            }
        }, 
        {
            u"$addFields": {
                u"errorQuote": {
                    u"$divide": [
                        u"$countError",
                        u"$count"
                    ]
                },
                u"warningQuote": {
                    u"$divide": [
                        u"$countWarning",
                        u"$count"
                    ]
                }
            }
        }, 
        {
            u"$match": {
                u"errorQuote": {
                    u"$gt": 0.7
                }
            }
        },
        {
            u"$project": {
                u"_id": 0
            }
        }
    ]

    cursor = collection.aggregate(
        pipeline, 
        allowDiskUse = False
    )
    
    result = [doc for doc in cursor]
    return result

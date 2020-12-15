db.getCollection("StatusMarketData").createIndex(
{ 
    "processor_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "result" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "error" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.message" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.request.exchange" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.request.call" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.request.args" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.request.args.symbol" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.request.request_timestamp" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.request.ticker_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.request.processor_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("StatusMarketData").createIndex(
{ 
    "details.request.request_id" : 1
},
{ 
    "background" : true
}
);
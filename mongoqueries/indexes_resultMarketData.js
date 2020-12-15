db.getCollection("ResultMarketData").createIndex(
{ 
    "exchange" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "call" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "args" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "args.symbol" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "request_timestamp" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "result_timestamp" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "ticker_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "result_processor_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "request_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("ResultMarketData").createIndex(
{ 
    "request_timestamp" : 1, 
    "lib" : 1, 
	"exchange" : 1, 
    "call" : 1, 
	"args" : 1, 
    "status" : 1
},
{ 
    "background" : true,
}
);
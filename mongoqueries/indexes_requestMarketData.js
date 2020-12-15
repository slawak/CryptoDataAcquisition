db.getCollection("RequestMarketData").createIndex(
{ 
    "exchange" : 1
},
{ 
    "background" : true
}
);
db.getCollection("RequestMarketData").createIndex(
{ 
    "call" : 1
},
{ 
    "background" : true
}
);
db.getCollection("RequestMarketData").createIndex(
{ 
    "args" : 1
},
{ 
    "background" : true
}
);
db.getCollection("RequestMarketData").createIndex(
{ 
    "args.symbol" : 1
},
{ 
    "background" : true
}
);
db.getCollection("RequestMarketData").createIndex(
{ 
    "request_timestamp" : 1
},
{ 
    "background" : true
}
);
db.getCollection("RequestMarketData").createIndex(
{ 
    "ticker_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("RequestMarketData").createIndex(
{ 
    "processor_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("RequestMarketData").createIndex(
{ 
    "request_id" : 1
},
{ 
    "background" : true
}
);
db.getCollection("RequestMarketData").createIndex(
{ 
    "request_timestamp" : 1,
    "lib" : 1, 
	"exchange" : 1, 
    "call" : 1, 
	"args" : 1,  
},
{ 
    "background" : true
}
);
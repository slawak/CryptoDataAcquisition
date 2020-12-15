let res = [
    db.dummy.insert({"dummy":"dummy item to ensure db exitsts. Can be safely removed."}),
    db.createUser(
      {
        user: "connect",
        pwd: "cryptoanalyzer!",
        roles: [
           { role: "readWrite", db: "MarketData" }
        ]
      }
    ),
 ]

printjson(res)
from fastapi import FastAPI, Query
from database import search
import uvicorn

app = FastAPI(title="Web Crawler API")

@app.get("/search")
def search_endpoint(
    query: str = Query(..., description="Arama kelimesi"),
    sortBy: str = Query("relevance", description="Sıralama kriteri")
):
    results = search(query)
    
    # Sıralama kuralı
    if sortBy == "relevance":
        # Halihazırda database.py içerisinde database'den çıkarken puana göre sıralanıyor
        pass
    
    return {
        "query": query,
        "count": len(results),
        "results": results
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3600)

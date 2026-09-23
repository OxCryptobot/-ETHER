            collection = payload.collection or self.default_collection

            if getattr(payload, "action", "") == "health" and self._client is None:
                h = {
                    "qdrant_url": self.qdrant_url,
                    "embed_model": self.embed_model,
                    "reachable": False,
                    "embed_ok": False,
                    "error": self._last_error or "offline",
                    "collections": {},
                }
                offline = CitrineResponse(
                    results=[
                        RetrievalResult(id="health", text="offline", score=0.0, metadata=h)
                    ],
                    collection=collection,
                    action="health",
                )
                return ResponseEnvelope(task_id=request.task_id, source_gem="citrine", payload=offline)

            if self.client is None:

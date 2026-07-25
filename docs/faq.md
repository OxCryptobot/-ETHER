# FAQ

**Do I need cloud APIs?**  
No. Default path is local Ollama + Docker.

**Why did sandbox fail with Docker not found?**  
Install Docker and ensure `docker ps` works. Clear Quartz needs it.

**Model not found errors?**  
`ollama pull <model>` and set `ETHER_PRIMARY_MODEL` in `.env`.

**Is Grandidierite safe?**  
Generated tools land in quarantine until you run `ether promote`.

**Can I run without Qdrant?**  
Yes. Memory features degrade; planning/coding/sandbox still work.

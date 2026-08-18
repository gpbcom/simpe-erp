# api

The HTTP entry point. Depends on `models` and `service`.

```
main.py               app, middleware order, router mounting
dependencies.py       wiring: sessions, repositories, services, guards
exception_handlers.py every MT* exception → its HTTP answer, once
middleware/           authentication, transaction
sse/                  the in-process notification fan-out
v1/                   the routers
```

**An endpoint contains no business logic.** It validates its payload, calls one
service method, and returns. Anything longer belongs a layer down.

**Middleware order is load-bearing.** CORS outermost, so a rejected credential
still carries the CORS headers. The transaction innermost, committing *before*
the response is written.

Authentication is middleware rather than a dependency, so a route added without
a guard is still authenticated. Authorisation stays in the per-route guards.

Router mount order matters in one place: the photograph router goes before the
assistant router, or `GET /{hca_id}` swallows `GET /photo-constraints`.

→ [docs/03](../../docs/03-api-reference.md), [docs/11](../../docs/11-security.md)

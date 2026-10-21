from app.main import app

routes = []
for route in app.routes:
    methods = getattr(route, 'methods', None)
    path = getattr(route, 'path', None)
    name = getattr(route, 'name', None)
    if methods:
        routes.append((list(methods), path, name))

routes.sort(key=lambda x: x[1])
print(f"Total routes: {len(routes)}")
for m, p, n in routes:
    print(f"{','.join(m):<20} {p:<45} {n}")

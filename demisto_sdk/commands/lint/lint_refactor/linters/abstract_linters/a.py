class a:
    X = 2

class b(a):
    def x(self, z):
        self.X = z

z = b()
zz = b()
print(a.X, z.X, zz.X)
z.x(1)
print(a.X, z.X, zz.X)
zz.x(3)
print(a.X, z.X, zz.X)
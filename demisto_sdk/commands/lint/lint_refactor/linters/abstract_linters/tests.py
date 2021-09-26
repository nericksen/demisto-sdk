# class a:
#     X = 0
#     @classmethod
#     def update(cls, x):
#         cls.X = x
# class b(a):
#     def k(self, k):
#         self.update(k)
# class c(a):
#     def k(self, k):
#         self.update(k)
#
# x = b()
# xx = b()
# xxx = c()
# xxxx = c()
# print(x.X, xx.X, xxx.X, xxxx.X)
# x.update(1)
# xx.update(2)
# xxx.update(3)
# xxxx.update(4)
# print(x.X, xx.X, xxx.X, xxxx.X)
import math
def solve(A):
    if A <= 1:
        return False if A < 0 else True
    digit_count = 0
    num = 1
    while num < A:
        num *= 10
        digit_count += 1
    reverse_sum = 0
    power = 10 ** (digit_count - 1)
    modulu = 10
    while digit_count > 0:
        next_digit = int(((A % modulu) // (modulu / 10)) * power)
        power /= 10
        reverse_sum += next_digit
        digit_count -= 1
        modulu *= 10
    return 1 if reverse_sum == A else 0
print(solve(2147447412))
1234
20000000000
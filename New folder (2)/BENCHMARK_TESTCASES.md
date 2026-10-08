# Py2SafeRust-X: Comprehensive Evaluation & Benchmark Suite (40 Test Cases)

This benchmark suite contains **40 carefully categorized test cases** designed to rigorously evaluate all 5 stages of the **Py2SafeRust-X** pipeline (Transpilation, Adaptive Repair, Semantic Verification, Explainable Compilation, and Confidence Assessment).

---

## 📊 Summary of Test Suite Spectrum

| Category | Topics Covered | Difficulty | Expected Pipeline Outcome |
| :--- | :--- | :--- | :--- |
| **1. Basic Python & Control Flow** | Arithmetic, conditionals, strings, loops | Easy | **PASS** (100% Score, 0 Repairs) |
| **2. Data Structures & Built-ins** | Lists, dicts, tuples, comprehensions | Easy–Med | **PASS** (100% Score) |
| **3. Functions & Modular Code** | Signatures, parameters, return types | Medium | **PASS** (Verified with 5–6 test cases) |
| **4. Recursion & Math Algorithms** | Factorial, Fibonacci, GCD, Euclidean | Medium | **PASS** (Boundary & recursive safety) |
| **5. Ownership & Borrow-Checker** | Vector aliasing, mutability, move semantics | Med–Hard | **REPAIRED / PASS** (Fixed by KB or LLM) |
| **6. Interactive User Input** | Single & multi-prompt `input()` streams | Medium | **PASS** (Evaluated over 5–6 dynamic inputs) |
| **7. Object-Oriented Programming (OOP)**| Classes, `__init__`, inheritance, `super()` | Med–Hard | **MIXED** (Simple: PASS / Advanced: FAIL) |
| **8. Exception Handling** | `try-except`, `raise`, `finally` | Hard | **FAIL / UNSUPPORTED** (Rust uses `Result`) |
| **9. Dynamic Typing & Corner Cases** | Type mutation, heterogeneous lists, `eval`| Hard | **FAIL / UNSUPPORTED** (Static typing violation)|

---

## 🟢 Category 1: Basic Python & Control Flow (Expected: PASS)

### Test 1: Simple Arithmetic & Direct Output
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** Variable assignment, binary operators, formatted printing.
```python
a = 15
b = 25
c = (a * 2) + (b // 5)
print(c)
```

### Test 2: Conditional Branching (If-Elif-Else)
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** Relational operators, boolean logic, nested branching.
```python
score = 85
if score >= 90:
    grade = "A"
elif score >= 80:
    grade = "B"
elif score >= 70:
    grade = "C"
else:
    grade = "F"
print(grade)
```

### Test 3: String Operations & Concatenation
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** String literals, `String` vs `&str`, concatenation.
```python
greeting = "Hello"
target = "World"
full = greeting + ", " + target + "!"
print(full)
```

### Test 4: While Loop with Accumulator
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** Loop conditions, in-place variable updates, inferred `let mut`.
```python
total = 0
i = 1
while i <= 10:
    total = total + i
    i = i + 1
print(total)
```

### Test 5: For Loop with `range()` and Step
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** Iteration over range, step intervals, modulo filtering.
```python
even_sum = 0
for n in range(0, 20):
    if n % 2 == 0:
        even_sum = even_sum + n
print(even_sum)
```

---

## 🟢 Category 2: Data Structures & Built-ins (Expected: PASS)

### Test 6: List Manipulation & Indexing
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** Vector initialization (`vec![]`), `.append() -> .push()`, indexing.
```python
nums = [10, 20, 30]
nums.append(40)
nums.append(50)
print(nums[0] + nums[3])
```

### Test 7: List Comprehension with Filter
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** List comprehension translation into Rust loop allocation.
```python
squares = [x * x for x in range(10) if x % 2 != 0]
print(squares)
```

### Test 8: Dictionary Lookup and Insertion
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** `std::collections::HashMap`, string keys, insert/access.
```python
capitals = {"France": "Paris", "Japan": "Tokyo"}
capitals["India"] = "New Delhi"
print(capitals["India"])
```

### Test 9: Tuple Packing and Unpacking
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** Rust tuple `(i64, i64)`, simultaneous unpacking assignment.
```python
a, b = 100, 200
a, b = b, a
print(a)
print(b)
```

### Test 10: Matrix / Nested List Traversal
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** `Vec<Vec<i64>>`, nested loop indexing.
```python
matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
diagonal_sum = 0
for i in range(3):
    diagonal_sum = diagonal_sum + matrix[i][i]
print(diagonal_sum)
```

---

## 🟢 Category 3: Functions & Modular Code (Expected: PASS)

### Test 11: Pure Arithmetic Function with Type Annotations
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Verified via 5–6 test cases)
* **What it tests:** Function signatures, Rust argument casting, return type.
```python
def multiply(x: int, y: int) -> int:
    return x * y
```

### Test 12: Function with Multiple Parameters and Internal Branching
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Verified via 5–6 test cases)
* **What it tests:** Function scope isolation, local variable declarations.
```python
def max_of_three(a: int, b: int, c: int) -> int:
    if a >= b and a >= c:
        return a
    elif b >= a and b >= c:
        return b
    else:
        return c
```

### Test 13: String Reversal and Palindrome Predicate
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Verified via 5–6 test cases)
* **What it tests:** String comparison, boolean return.
```python
def is_palindrome(s: str) -> bool:
    return s == s[::-1]
```

### Test 14: Composed Functions (Pipeline Logic)
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** Function calling another function, stack frames.
```python
def square(n: int) -> int:
    return n * n

def sum_of_squares(a: int, b: int) -> int:
    return square(a) + square(b)

print(sum_of_squares(3, 4))
```

---

## 🟢 Category 4: Recursion & Mathematical Algorithms (Expected: PASS)

### Test 15: Factorial Recursion (Boundary Safety)
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Verified via 5–6 non-negative test cases)
* **What it tests:** Recursive termination at `0` and `1`, integer multiplication.
```python
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
```

### Test 16: Fibonacci Sequence
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Verified via 5–6 test cases)
* **What it tests:** Multi-branch recursion (`fib(n-1) + fib(n-2)`).
```python
def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)
```

### Test 17: Greatest Common Divisor (Euclidean Algorithm)
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** While loop with modulo in function.
```python
def gcd(a: int, b: int) -> int:
    while b != 0:
        a, b = b, a % b
    return a

print(gcd(48, 18))
```

### Test 18: Recursive Sum of Digits
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Confidence: 100)
* **What it tests:** Division, modulo, single argument recursion.
```python
def sum_digits(n: int) -> int:
    if n == 0:
        return 0
    return (n % 10) + sum_digits(n // 10)

print(sum_digits(12345))
```

---

## 🟡 Category 5: Ownership, Borrowing & Move Semantics (Expected: REPAIRED / PASS)

### Test 19: Vector Aliasing / Move-After-Borrow Violation (E0382)
* **Difficulty:** Medium
* **Expected Outcome:** **REPAIRED** (Score: ~95, Pre-seeded KB / LLM inserts `.clone()`)
* **What it tests:** Rust move semantics vs Python reference semantics.
```python
x = [1, 2, 3]
y = x
print(x)
```

### Test 20: Reassignment of Immutable Binding (E0384)
* **Difficulty:** Easy–Med
* **Expected Outcome:** **REPAIRED** (Score: ~95, KB promotes `let` to `let mut`)
* **What it tests:** Detecting multiple assignments to the same identifier.
```python
val = 10
val = 20
print(val)
```

### Test 21: Simultaneous Read and Mutation in a Collection (E0502)
* **Difficulty:** Hard
* **Expected Outcome:** **REPAIRED** (Score: ~80–90, Restructures borrowing scope)
* **What it tests:** Borrow checker conflict between mutable borrow and immutable borrow.
```python
items = [1, 2, 3]
first = items[0]
items.append(4)
print(first)
print(items)
```

### Test 22: Redundant Mutability (`unused_mut`)
* **Difficulty:** Easy
* **Expected Outcome:** **PASS** (Score: 100, Strips redundant `mut` during cleanup)
* **What it tests:** Compiler diagnostic cleanup pass.
```python
read_only_list = [10, 20, 30]
print(read_only_list[1])
```

### Test 23: Mutation Across Function Scope Boundary
* **Difficulty:** Medium
* **Expected Outcome:** **PASS / REPAIRED**
* **What it tests:** Passing mutable vector into function for modification.
```python
def add_element(lst: list) -> list:
    lst.append(99)
    return lst

data = [1, 2, 3]
result = add_element(data)
print(result)
```

---

## 🔵 Category 6: Interactive User Input (`input()`) (Expected: PASS over 5–6 cases)

### Test 24: Single Integer Input & Arithmetic
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Generates 5–6 diverse test cases: 5, 2, 7, 0, etc.)
* **What it tests:** `__py2saferust_input`, `parse::<i64>()`, interactive terminal sessions.
```python
x = int(input("Enter number: "))
print(x * 2)
```

### Test 25: Multiple Prompt Interactive Addition
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Generates 5–6 multi-prompt test cases with terminal drawer)
* **What it tests:** Sequential stdin buffering, prompt-to-value reconstruction.
```python
a = int(input("Enter first number: "))
b = int(input("Enter second number: "))
print(a + b)
```

### Test 26: String User Input & Length Inspection
* **Difficulty:** Medium
* **Expected Outcome:** **PASS** (Generates 5–6 diverse string test cases including edge cases)
* **What it tests:** Stdin string reading without casting, `len()`.
```python
name = input("Enter your name: ")
print("Hello " + name + ", length is: " + str(len(name)))
```

---

## 🟠 Category 7: Object-Oriented Programming (OOP) (Expected: MIXED)

### Test 27: Self-Contained Class with Constructor & Method
* **Difficulty:** Medium
* **Expected Outcome:** **PASS / REPAIRED** (Score: ~75–85)
* **What it tests:** `struct`, `impl`, `&self`, direct execution verification.
```python
class Calculator:
    def __init__(self, base: int):
        self.base = base

    def add(self, n: int) -> int:
        return self.base + n

calc = Calculator(10)
print(calc.add(5))
```

### Test 28: Class with Multiple Fields & String Formatting
* **Difficulty:** Medium
* **Expected Outcome:** **PASS / REPAIRED**
* **What it tests:** Multiple struct fields, string conversion.
```python
class User:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

    def info(self) -> str:
        return self.name + " is " + str(self.age)

u = User("Alice", 25)
print(u.info())
```

### Test 29: Single Inheritance with `super()` Call
* **Difficulty:** Hard
* **Expected Outcome:** **PARTIAL / REPAIRED via LLM**
* **What it tests:** Flattening inheritance hierarchy into composition in Rust (`Animal` inside `Dog`).
```python
class Animal:
    def __init__(self, name: str):
        self.name = name

    def speak(self) -> str:
        return "Generic sound"

class Dog(Animal):
    def __init__(self, name: str, breed: str):
        super().__init__(name)
        self.breed = breed

    def speak(self) -> str:
        return "Woof!"

def main():
    pet = Dog("Buddy", "Golden")
    print(pet.speak())

main()
```

### Test 30: Multiple Inheritance via Trait Synthesis (Adaptive Repair Demo)
* **Difficulty:** Hard
* **Expected Outcome:** **REPAIRED / PASS** (Confidence: 65, Repair Log: 1)
* **What it demonstrates:** While Rust does not have class inheritance, the **Stage 2 Adaptive Repair Engine** detects multiple base classes and automatically maps them into **Rust Traits (`trait Flier`, `trait Swimmer`)** implemented on `struct Duck` (`impl Flier for Duck`, `impl Swimmer for Duck`), successfully compiling and achieving 100% semantic verification!
```python
class Flier:
    def fly(self):
        return "Flying"

class Swimmer:
    def swim(self):
        return "Swimming"

class Duck(Flier, Swimmer):
    pass

d = Duck()
print(d.fly())
print(d.swim())
```


### Test 31: Dynamic Polymorphism with Heterogeneous List (CORNER CASE - Expected: FAIL)
* **Difficulty:** Hard
* **Expected Outcome:** **FAIL / UNSUPPORTED**
* **Why it fails:** Rust vectors cannot store heterogeneous structs without `Box<dyn Trait>` or enum dispatch.
```python
class Cat:
    def sound(self): return "Meow"

class Dog:
    def sound(self): return "Bark"

animals = [Cat(), Dog()]
for a in animals:
    print(a.sound())
```

### Test 32: Dynamic Monkey-Patching / Field Injection (CORNER CASE - Expected: FAIL)
* **Difficulty:** Hard
* **Expected Outcome:** **FAIL**
* **Why it fails:** In Rust, all struct fields must be declared at compile-time.
```python
class Point:
    def __init__(self, x: int):
        self.x = x

p = Point(10)
p.y = 20  # Injected dynamically outside __init__
print(p.x + p.y)
```

---

## 🔴 Category 8: Exception Handling (Expected: FAIL / UNSUPPORTED)

### Test 33: Simple `try-except ZeroDivisionError` (CORNER CASE - Expected: FAIL)
* **Difficulty:** Medium
* **Expected Outcome:** **FAIL / UNSUPPORTED**
* **Why it fails:** Rust has no `try-catch` mechanism; division by zero triggers a `panic!` rather than an exception.
```python
try:
    x = 10 / 0
    print(x)
except ZeroDivisionError:
    print("Caught division by zero")
```

### Test 34: Raising Custom Exceptions (CORNER CASE - Expected: FAIL)
* **Difficulty:** Medium
* **Expected Outcome:** **FAIL / UNSUPPORTED**
* **Why it fails:** Rust returns `Result<T, E>` types instead of unwinding stack frames via `raise`.
```python
def check_positive(n: int) -> int:
    if n < 0:
        raise ValueError("Number must be positive")
    return n

print(check_positive(-5))
```

### Test 35: `try-except-finally` Resource Cleanup (CORNER CASE - Expected: FAIL)
* **Difficulty:** Hard
* **Expected Outcome:** **FAIL / UNSUPPORTED**
* **Why it fails:** Rust enforces cleanup deterministically via the `Drop` trait, not `finally` blocks.
```python
total = 0
try:
    total = total + 10
except Exception:
    total = total - 1
finally:
    total = total * 2
print(total)
```

---

## 🔴 Category 9: Dynamic Python Typing & Advanced Edge Cases (Expected: FAIL)

### Test 36: Dynamic Variable Type Re-binding (CORNER CASE - Expected: FAIL)
* **Difficulty:** Medium
* **Expected Outcome:** **FAIL**
* **Why it fails:** Python variables are dynamic labels; Rust variables are statically typed at declaration.
```python
x = 42
print(x)
x = "Now I am a string!"
print(x)
```

### Test 37: Heterogeneous List Literals (CORNER CASE - Expected: FAIL)
* **Difficulty:** Medium
* **Expected Outcome:** **FAIL**
* **Why it fails:** Rust `Vec<T>` demands a single homogenous type `T`.
```python
mixed = [1, "two", 3.14, True]
print(mixed)
```

### Test 38: Built-in `eval()` Dynamic Metaprogramming (CORNER CASE - Expected: FAIL)
* **Difficulty:** Hard
* **Expected Outcome:** **FAIL**
* **Why it fails:** Rust is an ahead-of-time (AOT) compiled language without an embedded runtime interpreter.
```python
expr = "5 * 10 + 2"
print(eval(expr))
```

### Test 39: Arbitrary Variable Argument Packing (`*args`, `**kwargs`) (CORNER CASE - Expected: FAIL)
* **Difficulty:** Hard
* **Expected Outcome:** **FAIL**
* **Why it fails:** Rust requires concrete, fixed-arity function signatures (or macros).
```python
def flexible_sum(*args):
    total = 0
    for v in args:
        total = total + v
    return total

print(flexible_sum(1, 2, 3, 4, 5))
```

### Test 40: Generator Function with `yield` (CORNER CASE - Expected: FAIL)
* **Difficulty:** Hard
* **Expected Outcome:** **FAIL**
* **Why it fails:** Python generators require state machine coroutine transformations (`Iterator` trait implementation).
```python
def count_up(n):
    i = 1
    while i <= n:
        yield i
        i = i + 1

for val in count_up(5):
    print(val)
```

---

## 💡 How to Use This Benchmark File in Your Presentation & Defense

1. **For Live Demonstrations (Guaranteed 100% Success):**
   * Use **Tests 1, 2, 6, 7, 11, 15, 24, 25**.
   * These showcase clean transpilation, dual-runtime stdout parity, and automatic verification over 5–6 dynamic inputs.

2. **For Showing Off Adaptive Repair & Self-Learning:**
   * Use **Tests 19, 20, 21**.
   * These demonstrate the compiler-directed repair loop resolving `E0382` (move-after-borrow) and `E0384` (mutability) without manual intervention.

3. **For Future Work / Limitations Defense:**
   * Reference **Tests 30, 33, 36, 38**.
   * Transparently explaining *why* dynamic features (`eval`, `try-except`, multiple inheritance) fail in statically typed Rust demonstrates profound academic understanding of language semantics.

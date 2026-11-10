---
description: 'Generic code review instructions, customizable for any project using GitHub Copilot. Covers C, C++, Fortran, Python, and Bash review checks, testing strategy, security, performance, and architecture.'
applyTo: ["**/*.c", "**/*.h", "**/*.cpp", "**/*.cc", "**/*.cxx", "**/*.hpp", "**/*.hh", "**/*.f", "**/*.for", "**/*.f90", "**/*.F", "**/*.F90", "**/*.py", "**/*.sh", "**/*.bash"]
excludeAgent: ["coding-agent"]
---

# Generic Code Review Instructions

Comprehensive code review guidelines for GitHub Copilot that can be adapted to any project. These instructions follow best practices from prompt engineering and provide a structured approach to code quality, security, testing, and architecture review, with per-language guidance for C, C++, Fortran, Python, and Bash.

## Review Language

When performing a code review, respond in **English** (or specify your preferred language).

> **Customization Tip**: Change to your preferred language by replacing "English" with "Portuguese (Brazilian)", "Spanish", "French", etc.

## Review Scope by Language

When performing a code review, apply **only** the language subsections that match the files in the diff, plus the language-agnostic sections. Do not raise findings that belong to a language absent from the change.

## Review Priorities

When performing a code review, prioritize issues in the following order:

### 🔴 CRITICAL (Block merge)
- **Security**: Vulnerabilities, exposed secrets, authentication/authorization issues
- **Memory Safety**: Buffer overflows, use-after-free, leaks of owning resources, unbounded copies
- **Undefined Behaviour**: Uninitialized reads, signed overflow, aliasing violations, out-of-bounds indexing, ignored `allocate`/`malloc` status
- **Correctness**: Logic errors, data corruption risks, race conditions, exact `==` comparisons on floating-point results
- **Breaking Changes**: API contract changes without versioning
- **Data Loss**: Risk of data loss or corruption
- **Silent Failure**: Errors swallowed, exit statuses dropped, or a scheduler job reporting success for a failed run

### 🟡 IMPORTANT (Requires discussion)
- **Code Quality**: Severe violations of SOLID principles, excessive duplication
- **Test Coverage**: Missing tests for critical paths or new functionality
- **Performance**: Obvious performance bottlenecks (N+1 queries, memory leaks)
- **Architecture**: Significant deviations from established patterns

### 🟢 SUGGESTION (Non-blocking improvements)
- **Readability**: Poor naming, complex logic that could be simplified
- **Optimization**: Performance improvements without functional impact
- **Best Practices**: Minor deviations from conventions
- **Documentation**: Missing or incomplete comments/documentation

## General Review Principles

When performing a code review, follow these principles:

1. **Be specific**: Reference exact lines, files, and provide concrete examples
2. **Provide context**: Explain WHY something is an issue and the potential impact
3. **Suggest solutions**: Show corrected code when applicable, not just what's wrong
4. **Be constructive**: Focus on improving the code, not criticizing the author
5. **Recognize good practices**: Acknowledge well-written code and smart solutions
6. **Be pragmatic**: Not every suggestion needs immediate implementation
7. **Group related comments**: Avoid multiple comments about the same topic

## Code Quality Standards

When performing a code review, check for:

### Clean Code
- Descriptive and meaningful names for variables, functions, and classes
- Single Responsibility Principle: each function/class does one thing well
- DRY (Don't Repeat Yourself): no code duplication
- Functions should be small and focused (ideally < 20-30 lines)
- Avoid deeply nested code (max 3-4 levels)
- Avoid magic numbers and strings (use constants)
- Code should be self-documenting; comments only when necessary

### Examples
```javascript
// ❌ BAD: Poor naming and magic numbers
function calc(x, y) {
    if (x > 100) return y * 0.15;
    return y * 0.10;
}

// ✅ GOOD: Clear naming and constants
const PREMIUM_THRESHOLD = 100;
const PREMIUM_DISCOUNT_RATE = 0.15;
const STANDARD_DISCOUNT_RATE = 0.10;

function calculateDiscount(orderTotal, itemPrice) {
    const isPremiumOrder = orderTotal > PREMIUM_THRESHOLD;
    const discountRate = isPremiumOrder ? PREMIUM_DISCOUNT_RATE : STANDARD_DISCOUNT_RATE;
    return itemPrice * discountRate;
}
```

```c
/* ❌ BAD: cryptic names, magic numbers, no width-stable types */
double calc(int x, double y) { return x > 100 ? y * 0.15 : y * 0.10; }

/* ✅ GOOD: named constants, intent-revealing names, fixed-width types */
#define PREMIUM_ORDER_THRESHOLD 100
static const double PREMIUM_DISCOUNT_RATE = 0.15;
static const double STANDARD_DISCOUNT_RATE = 0.10;

double calculate_discount(int32_t order_total, double item_price) {
    const double rate = order_total > PREMIUM_ORDER_THRESHOLD
                            ? PREMIUM_DISCOUNT_RATE
                            : STANDARD_DISCOUNT_RATE;
    return item_price * rate;
}
```

```cpp
// ❌ BAD: out-parameters, unclear units, silent narrowing conversion
void discount(int total, double price, double &out) {
    out = total > 100 ? price * 0.15 : price * 0.10;
}

// ✅ GOOD: strong types for units, value return, named constants
constexpr MoneyCents kPremiumThreshold{100};
constexpr double kPremiumDiscountRate = 0.15;
constexpr double kStandardDiscountRate = 0.10;

[[nodiscard]] MoneyCents CalculateDiscount(const OrderTotal &total,
                                           const MoneyCents &item_price) {
    const double rate = total > kPremiumThreshold ? kPremiumDiscountRate
                                                  : kStandardDiscountRate;
    return item_price * rate;
}
```

```fortran
! ❌ BAD: no constants, positional-only args, undocumented units
      function calc(x, y) result(r)
      real :: x, y, r
      if (x > 100) then
        r = y * 0.15
      else
        r = y * 0.10
      end if
      end function

! ✅ GOOD: module with named parameters, explicit intent, kind parameters
module discounts
  use, intrinsic :: iso_fortran_env, only: real64
  implicit none (type, external)
  private
  public :: calculate_discount
  real(real64), parameter :: premium_threshold = 100.0_real64
  real(real64), parameter :: premium_rate = 0.15_real64
  real(real64), parameter :: standard_rate = 0.10_real64
contains
  function calculate_discount(order_total, item_price) result(discount)
    real(real64), intent(in) :: order_total   ! order value in USD
    real(real64), intent(in) :: item_price    ! unit price in USD
    real(real64)             :: discount
    if (order_total > premium_threshold) then
      discount = item_price * premium_rate
    else
      discount = item_price * standard_rate
    end if
  end function calculate_discount
end module discounts
```

```python
# ❌ BAD: magic numbers, untyped signature, unclear argument order
def calc(x, y):
    return y * 0.15 if x > 100 else y * 0.10


# ✅ GOOD: named constants, type hints, keyword-only where order is ambiguous
PREMIUM_THRESHOLD_USD = 100.0
PREMIUM_DISCOUNT_RATE = 0.15
STANDARD_DISCOUNT_RATE = 0.10


def calculate_discount(*, order_total_usd: float, item_price_usd: float) -> float:
    """Return the discount on one item for the given order total."""
    rate = (
        PREMIUM_DISCOUNT_RATE
        if order_total_usd > PREMIUM_THRESHOLD_USD
        else STANDARD_DISCOUNT_RATE
    )
    return item_price_usd * rate
```

### Error Handling
- Proper error handling at appropriate levels
- Meaningful error messages
- No silent failures or ignored exceptions
- Fail fast: validate inputs early
- Use appropriate error types/exceptions
- Report failures on the correct channel: `stderr` (Fortran `error_unit`, C `fprintf(stderr, …)`, shell `>&2`), never swallowed or mixed into data output

### Examples
```python
# ❌ BAD: Silent failure and generic error
def process_user(user_id):
    try:
        user = db.get(user_id)
        user.process()
    except:
        pass


# ✅ GOOD: Explicit error handling
def process_user(user_id):
    if not user_id or user_id <= 0:
        raise ValueError(f"Invalid user_id: {user_id}")

    try:
        user = db.get(user_id)
    except UserNotFoundError:
        raise UserNotFoundError(f"User {user_id} not found in database")
    except DatabaseError as e:
        raise ProcessingError(f"Failed to retrieve user {user_id}: {e}")

    return user.process()
```

```c
/* ❌ BAD: return value ignored, no way for the caller to know what failed */
int read_config(const char *path) {
    FILE *f = fopen(path, "r");
    char buf[256];
    fscanf(f, "%255s", buf);
    fclose(f);
    return 0;
}

/* ✅ GOOD: fail fast, distinct error codes, message on stderr, single cleanup label */
int read_config(const char *path) {
    if (path == NULL || *path == '\0') return -EINVAL;

    FILE *f = fopen(path, "r");
    if (f == NULL) {
        fprintf(stderr, "read_config: cannot open %s: %s\n", path, strerror(errno));
        return -errno;
    }

    char buf[256];
    int rc = (fscanf(f, "%255s", buf) == 1) ? 0 : -EBADMSG;
    fclose(f);

    if (rc != 0) fprintf(stderr, "read_config: malformed file: %s\n", path);
    return rc;
}
```

```cpp
// ❌ BAD: error code stored in a member nobody checks, exception type lost
void load_mesh(const std::string &path) {
    try { read(path); } catch (...) { last_error_ = -1; }
}

// ✅ GOOD: typed error with context, caller decides how to recover
void load_mesh(std::string_view path) {
    try {
        ReadMesh(path);
    } catch (const MeshParseError &e) {
        throw MeshLoadError(path, e.line(), e.what());
    } catch (const std::io_error &e) {
        throw MeshLoadError(path, std::nullopt, e.what());
    }
}
```

```fortran
! ❌ BAD: I/O status ignored, program continues with undefined data
      open(unit=10, file=infile)
      read(10, *) nx, ny
      close(10)

! ✅ GOOD: iostat/errmsg checked, failure reported on error_unit with a non-zero exit
open(unit=10, file=infile, action='read', iostat=istat, iomsg=iomsg)
if (istat /= 0) then
  write (error_unit, '(a,i0,a,a)') 'setup: open failed, iostat=', istat, ': ', iomsg
  stop 1
end if

read(10, *, iostat=istat, iomsg=iomsg) nx, ny
if (istat /= 0) then
  write (error_unit, '(a,a)') 'setup: cannot read grid size: ', trim(iomsg)
  stop 1
end if
close(10)
```

```bash
# ❌ BAD: failure invisible, empty value propagates
value=$(extract_field "$file")
process "$value"

# ✅ GOOD: checked command substitution, error on stderr, explicit exit code
value=$(extract_field "$file") || {
  printf '%s: extract_field failed for %s\n' "$0" "$file" >&2
  exit 1
}
[[ -n $value ]] || { printf '%s: empty field in %s\n' "$0" "$file" >&2; exit 1; }
process "$value"
```

## Security Review

When performing a code review, check for security issues:

- **Sensitive Data**: No passwords, API keys, tokens, or PII in code or logs
- **Input Validation**: All user inputs are validated and sanitized
- **SQL Injection**: Use parameterized queries, never string concatenation
- **Command Injection**: No `system()`, shell interpolation, or `eval` on untrusted input
- **Memory Safety**: No unbounded copies, unsized buffers, or format strings built from input
- **Authentication**: Proper authentication checks before accessing resources
- **Authorization**: Verify user has permission to perform action
- **Cryptography**: Use established libraries, never roll your own crypto
- **Dependency Security**: Check for known vulnerabilities in dependencies

### Examples
```java
// ❌ BAD: SQL injection vulnerability
String query = "SELECT * FROM users WHERE email = '" + email + "'";

// ✅ GOOD: Parameterized query
PreparedStatement stmt = conn.prepareStatement(
    "SELECT * FROM users WHERE email = ?"
);
stmt.setString(1, email);
```

```javascript
// ❌ BAD: Exposed secret in code
const API_KEY = "sk_live_abc123xyz789";

// ✅ GOOD: Use environment variables
const API_KEY = process.env.API_KEY;
```

```c
/* ❌ BAD: attacker-controlled format string and unbounded copy */
printf(user_input);
strcpy(dest, user_input);
system(command_from_config);

/* ✅ GOOD: fixed format, bounded copy with termination, no shell involved */
fputs(user_input, stdout);                    /* or printf("%s", user_input) */
if (snprintf(dest, sizeof dest, "%s", user_input) >= (int)sizeof dest) {
    return -ENAMETOOLONG;                     /* input truncated, refuse it */
}
const char *argv[] = { TOOL_PATH, arg, NULL };
execv(TOOL_PATH, argv);                       /* no shell parsing of argv */
```

```cpp
// ❌ BAD: unchecked length feeds a raw buffer; secret written to the log
char buf[64];
memcpy(buf, payload.data(), payload_size);
std::cout << "token=" << token << '\n';

// ✅ GOOD: sized container, bounds validated first, secret redacted
if (payload_size > kMaxPayloadBytes) throw ProtocolError("payload too large");
std::vector<char> buf(payload_size);
std::copy_n(payload.begin(), payload_size, buf.begin());
std::cout << "token=" << Redact(token) << '\n';
```

```fortran
! ❌ BAD: attacker-controlled format string, fixed buffer with no length check
      write(6, fmt_from_user) secret
      character(len=16) :: name
      read(5, '(a)') name       ! silently truncates longer input

! ✅ GOOD: literal format, sized buffer, input validated before use
write (unit=output, fmt='(a)') trim(redacted_value)

character(len=max_name_len) :: name
read (unit=input, fmt='(a)', iostat=istat) name
if (istat /= 0 .or. len_trim(name) == 0) then
  write (error_unit, '(a)') 'input: missing or unreadable name'
  stop 1
end if
if (index(name, '/../') /= 0) then
  write (error_unit, '(a)') 'input: path traversal rejected'
  stop 1
end if
```

```python
# ❌ BAD: unsafe deserialization and shell interpolation
model = pickle.load(open(upload_path, "rb"))
subprocess.run(f"plot.py {user_arg}", shell=True)
api_key = "sk_live_abc123xyz789"

# ✅ GOOD: safe loaders, argument lists, secrets from the environment
model = torch.load(upload_path, weights_only=True)
subprocess.run(["plot.py", user_arg], shell=False, check=True)
api_key = os.environ["API_KEY"]
```

```bash
# ❌ BAD: eval on untrusted input, secret echoed, pipe-to-shell install
eval "$user_supplied_command"
echo "using token $GITHUB_TOKEN"
curl -fsSL https://example.com/install.sh | bash

# ✅ GOOD: no eval, no secret disclosure, reviewed script executed locally
"$TOOL_BIN" -- "$user_argument"          # argv only, never re-parsed by the shell
printf 'using token: %s\n' "$(redact "$GITHUB_TOKEN")"
curl -fsSL -o /tmp/install.sh https://example.com/install.sh
less /tmp/install.sh                      # human review before execution
bash /tmp/install.sh
```

## Testing Standards

When performing a code review, verify that tests are a deliberate part of the change, not an afterthought. These principles are language-agnostic; per-language tooling follows below.

### Language-Agnostic Principles

- **Coverage of risk**: every new behaviour, and every branch of a changed function, has a test; critical paths (I/O, numerics, allocations, parallel regions) are tested before cosmetics are
- **Descriptive names**: the test name states the condition and the expected result
- **Structured body**: clear Arrange-Act-Assert or Given-When-Then; one behaviour per test
- **Specific assertions**: assert on the value/shape/state, not "it did not crash"; avoid generic assertTrue/assertFalse
- **Edge cases**: zero, one, max, empty, null, negative, NaN/Inf, misaligned sizes, boundary indices, off-by-one loop limits, single-rank and multi-rank runs
- **Error paths**: allocation failure, missing file, malformed input, and non-zero exit statuses are exercised, not only the happy path
- **Independence and determinism**: no order dependence, no wall-clock or network reliance, fixed seeds for randomness, temporary files in a scratch directory
- **Mock at the boundary**: mock external services and filesystems; never mock the logic under test
- **Numerical honesty**: compare floating-point results with a documented tolerance (`rtol`/`atol`) or bit-reproducibility against a baseline — never with `==`
- **Parallel and accelerator parity**: results must match between the serial build and the threaded/MPI/GPU build, and across rank and thread counts
- **CI enforcement**: tests run in CI on every supported compiler/interpreter version, with warnings-as-errors and, where feasible, a sanitizer build; a failing test blocks merge

### Examples

```cpp
// ❌ BAD: vague name, no real assertion, exact float comparison
test('test1') {
    auto r = calc(5, 10);
    ASSERT_TRUE(r.ok());
}

// ✅ GOOD: describes the case, asserts the value, uses a tolerance
TEST(DiscountTest, AppliesStandardRateBelowPremiumThreshold) {
    const Discount d{.order_total = 50.0, .item_price = 20.0};

    const double discount = CalculateDiscount(d);

    EXPECT_DOUBLE_EQ(discount, 2.0);
}
```

### Per-Language Testing Expectations

**C**

- Unit tests with Unity (+ CMock/FFF for stubs), Check, or GoogleTest; wired to CTest/Meson/Make so `make test` or `meson test` runs them
- The test build enables `-fsanitize=address,undefined,leak` and at least one CI job runs Valgrind or the sanitizers; leaks and undefined behaviour are test failures, not warnings
- Input-parsing, string, and file-handling code should have fuzz targets (libFuzzer/AFL++); regressions found by fuzzing must be added as unit tests
- Coverage via `gcov`/`lcov`/`gcovr`, reporting line **and branch** coverage, since C bugs cluster in untested error branches
- Tests compile with `-Wall -Wextra -Werror` and the project's `-std=c17` (or equivalent) so warnings cannot silently enter the codebase

**C++**

- GoogleTest/GoogleMock, Catch2, or doctest, registered with CTest (`add_test`, `gtest_discover_tests`) so CI discovers them
- Prefer compile-time checks where possible: `static_assert` and `constexpr` tests for pure logic
- Threaded code must have a ThreadSanitizer job; ownership code an ASan/LSan job; `-fsanitize=undefined` for UB. Rule-of-five types are exercised by copy, move, and copy-assignment tests
- Property-based tests (RapidCheck) for numeric kernels, serializers, and invariants
- Coverage with `gcovr` or `llvm-cov`; diff coverage on new code is the more useful gate

**Fortran**

- Use `fpm test` (test executables under `test/`, non-zero exit = failure) or a framework: pFUnit (JUnit-style, CMake, MPI-aware), test-drive, or FRUIT; `pytest-fortran` fits teams already living in pytest
- Legacy/monolithic codes without a unit-test seam require a **golden-file regression test**: run on a fixed input set, compare against a baseline with documented tolerance, plus a bit-reproducibility check at the same rank count
- Debug/test builds must use `-fcheck=all` (bounds, do, mem, pointer, recursion), `-ffpe-trap=invalid,zero,overflow`, `-warn`, `-traceback` (oneAPI: `-check all -fpe0 -traceback`); tests run against such a build, not only the optimized `-O3 -ffast-math` production build
- MPI code is tested at `-np 1`, `-np 2`, and a non-square/decomposed rank count, and compared against the serial result
- Coverage via `gfortran -fprofile-arcs -ftest-coverage` with `gcov`/`gcovr` (line coverage only)

**Python**

- pytest with fixtures, `@pytest.mark.parametrize` for tables of cases, `tmp_path` for files, and `monkeypatch`/`unittest.mock` only at I/O boundaries
- Scientific code uses `numpy.testing.assert_allclose` with explicit `rtol`/`atol`, shape/dtype assertions, and seeded RNG (`np.random.default_rng(seed)`); property-based tests with Hypothesis for numerical invariants
- Coverage with `pytest-cov` and a `--cov-fail-under` gate; static gates with `ruff`/`flake8` and `mypy`/Pylance on changed modules
- The suite runs across the project's supported version matrix (tox/nox); no test may depend on a developer's local environment, notebook state, or network
- Doctests are acceptable only for documented public API examples and must run in CI (`--doctest-modules`)

**Bash**

- `shellcheck` clean in CI (with `-x` for sourced files, severity gates raised rather than lowered) and `bash -n` for a syntax pass on every script; suppression comments require a stated reason
- Tests with `bats-core` (or `shellspec`/`shunit2`); scripts are sourceable so functions are tested directly via the `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]` main guard, and entry-point behaviour is tested by asserting exit code, stdout, and stderr separately
- External commands are faked, not mocked in-process: a test-local `bin/` prepended to `PATH` with stub `sbatch`, `srun`, `module`, `mpirun`, `rsync` scripts that echo their arguments and return a controlled status. Stubs assert the flags the script passed, not merely that they ran
- Each test uses `mktemp -d` for its workspace with `trap` cleanup; no test writes to the repo, `$HOME`, or shared scratch, and none depends on the developer's environment modules
- Failure paths are required: missing argument, unknown option, missing dependency (`command -v` fails), unreadable input, non-zero exit from the wrapped application, and interrupt/cleanup behaviour
- Matrix coverage: bash 3.2 (macOS default) and 5.x, plus `dash`/`sh` when POSIX compatibility is claimed; run with spaces, globs, and non-UTF-8 characters in filenames, and with `IFS`/locale varied
- HPC job scripts cannot execute in CI, so require a lint/verify step instead: directives parsed for consistency (task counts vs `srun`, `OMP_NUM_THREADS` vs `--cpus-per-task`, valid time format, pinned module versions) plus a documented smoke test on a debug/small partition
- Optional but valuable: `kcov`/`bashcov` line coverage for release-critical scripts, and a regression test added for every production incident a script caused

## Language-Specific Review

When performing a code review, apply the checks for the language(s) in the diff.

### C

**Memory and lifetime**

- Every `malloc`/`calloc`/`strdup` return value is checked; every allocation has a matching `free` on all paths, including error paths (a single `goto fail;` cleanup label is idiomatic)
- No use-after-free, double free, or returning pointers to stack memory
- `sizeof *ptr` preferred over `sizeof(Type)` so the allocation tracks type changes
- Ownership of returned strings/structs is documented in the header comment

**Buffers and strings**

- No `strcpy`, `strcat`, `sprintf`, `vsprintf`, `gets`, or `alloca` in untrusted paths; use `snprintf`, `strlcpy`/`strncpy` with explicit NUL termination
- Array and index arithmetic bounds-checked; `size_t`/`ptrdiff_t` used for sizes and differences, `stdint.h` types (`int32_t`, `uint64_t`) where width matters
- `read`/`fread`/`recv` return values compared against the requested count; buffers NUL-terminated before string use

**Undefined behaviour and portability**

- No uninitialized reads, signed-overflow arithmetic, aliasing violations, shifting by >= the type width, or reliance on evaluation order
- No non-standard extensions unless guarded (`#ifdef`), and the required standard is stated in the build (`-std=c17`)
- `errno` is cleared before the call and read only where the API defines it; `char` signedness, `assert()` side effects, and function-pointer casts are reviewed
- Headers use include guards or `#pragma once`, declare prototypes for all externs, and contain no definitions or mutable globals

**Security**

- No `system()`, `popen()`, or unsanitized format strings (`printf(user_input)`)
- File paths validated; `fopen` modes checked; no secrets in code, environment dumps, or logs

#### Examples

```c
/* ❌ BAD: unchecked allocation, unbounded copy, leak on the error path */
int load_record(const char *name, Record *out) {
    char buf[32];
    strcpy(buf, name);                 /* overflow if strlen(name) >= 32 */
    Record *r = malloc(sizeof *r);     /* NULL never checked */
    r->name = strdup(buf);
    if (!out) return -1;               /* r and r->name leaked */
    *out = *r;
    free(r);                           /* r->name never freed */
    return 0;
}

/* ✅ GOOD: validated inputs, bounded copy, checked allocation, clear ownership */
#define MAX_NAME 32                    /* buf size must equal this limit */

int load_record(const char *name, Record *out) {
    if (name == NULL || out == NULL) return -EINVAL;

    char buf[MAX_NAME];
    int n = snprintf(buf, sizeof buf, "%s", name);
    if (n < 0 || (size_t)n >= sizeof buf) return -ENAMETOOLONG;

    out->name = strdup(buf);           /* caller owns and must free() */
    if (out->name == NULL) return -ENOMEM;
    return 0;
}
```

### C++

**Resource management**

- RAII everywhere: no owning raw `new`/`delete`; `std::make_unique`/`std::make_shared` or containers instead. Rule of zero preferred; if a class owns a resource, all five special members are handled (`= default`/`= delete` where appropriate)
- No dangling views: `std::string_view`, `std::span`, and iterators must not outlive their backing store, and functions must not return references to locals or temporaries
- Containers used over manual arrays; `reserve()` before known-count `push_back`; `emplace_back` where it avoids a temporary

**Correctness**

- Bounds-safe access via `at()`, `span`, or a checked index; no C-style casts to paper over types — prefer `static_cast`/`gsl::not_null` and document why `reinterpret_cast` is needed
- `const` correctness (members, parameters, `override`, `noexcept` on moves); pass by `const&` or `string_view`, return by value
- Virtual calls in constructors/destructors, object slicing by value, and shadowing are flagged; `override`/`final` used explicitly
- Exceptions: destructors and swap are `noexcept`; the error path uses the right type; no `catch (...)` that swallows without logging or rethrowing with context

**Concurrency**

- No manual `lock()`/`unlock()`: use `std::scoped_lock`/`lock_guard`; shared state protected, and destruction order relative to threads considered
- Data races in `parallel_for`/TBB/OpenMP-equivalent code reviewed for reduction and first-touch issues

**Build and tooling**

- The project's standard (`-std=c++17/20/23`) is consistent across targets; headers are self-contained and include-what-you-use
- `clang-tidy`, `-Wall -Wextra -Wpedantic -Werror`, and sanitizer/TSan CI jobs are expected

#### Examples

```cpp
// ❌ BAD: manual ownership that leaks if compute() throws, unchecked indexing,
//        reference to a destroyed temporary
double *buf = new double[n];
compute(buf, n);
delete[] buf;

const std::string& out_path(const std::string &stem) {
    return stem + ".out";              // reference to a destroyed temporary
}

// ✅ GOOD: RAII container, size from the container, value return
std::vector<double> buf(n);
compute(buf.data(), buf.size());

std::string out_path(const std::string &stem) { return stem + ".out"; }
```

### Fortran

**Module hygiene and typing**

- `implicit none` in every program unit (Fortran 2018 `implicit none (type, external)` where supported); no `COMMON`, no `INCLUDE` of source — use `module` + `use` so interfaces are explicit
- `intent(in/out/inout)` on all dummy arguments; `private` default with an explicit `public` list
- Kind parameters instead of `real*8`/`double precision`: `use, intrinsic :: iso_fortran_env` and `real(real64)`; literals suffixed (`1.0e0_real64`) so no silent precision loss occurs
- Character lengths and `intent(inout)` string truncation checked; `optional` arguments always guarded by `present()`

**Arrays and numerics**

- Explicit-shape/assumed-size (`a(*)`, `a(n)`) declarations reviewed against actual call sites; prefer assumed-shape `a(:)`; no out-of-bounds, negative, or zero-based indexing carried over from C
- Allocatables use `allocate(..., stat=, errmsg=)` with checked status, deallocated on error paths, and large arrays not left allocated across timesteps
- The leftmost (fastest-varying) index must be innermost for unit stride; array expressions and `where` preferred over element loops; `do concurrent` and `!$omp` regions reviewed for independent iterations and reduction races
- No `==` on reals: use an absolute/relative tolerance; NaN/Inf handling stated; reduction order and its effect on reproducibility documented; no `GO TO`-driven control flow in new code

**Build and tooling**

- Consistent free-form source, file suffixes, and compile flags; interfaces for any `bind(C)` boundary checked against the C declaration
- Debug/test builds use `-fcheck=all -ffpe-trap=invalid,zero,overflow -warn all -traceback`; optimized builds must not add `-ffast-math`/`-Ofast` unless the numerical tolerance impact is reviewed and accepted

#### Examples

```fortran
! ❌ BAD: implicit typing, non-portable kind, exact float compare, unchecked allocate,
!         inner loop on the slowest-varying index
      subroutine scale(a, b, n, m, c)
      real*8 a(m, n), b(m, n), c
      common /ws/ w
      allocate(w(n))
      do i = 1, m
        do j = 1, n
          a(i, j) = b(i, j) * c
        end do
      end do
      if (a(1, 1) == 0.0d0) write (*, *) 'zero'
      end subroutine

! ✅ GOOD: module + explicit interface, kind parameters, checked allocate,
!          unit-stride inner loop, tolerance-based comparison
module scaling
  use, intrinsic :: iso_fortran_env, only: real64, error_unit
  implicit none (type, external)
  private
  public :: scale
contains
  subroutine scale(a, b, c)
    real(real64), intent(out) :: a(:, :)
    real(real64), intent(in)  :: b(:, :)
    real(real64), intent(in)  :: c
    real(real64), parameter   :: tiny_val = 1.0e-14_real64
    real(real64), allocatable :: work(:)
    integer                   :: i, j, istat
    character(len=512)        :: emsg

    if (any(shape(a) /= shape(b))) then
      write (error_unit, '(a)') 'scale: shape mismatch between a and b'
      stop 1
    end if

    allocate (work(size(b, 1)), stat=istat, errmsg=emsg)
    if (istat /= 0) then
      write (error_unit, '(a,i0,a,a)') 'scale: allocate failed, stat=', istat, ': ', emsg
      stop 1
    end if

    do j = 1, size(b, 2)
      work = b(:, j) * c          ! leftmost index is contiguous -> vectorized
      do i = 1, size(b, 1)
        a(i, j) = work(i)
      end do
    end do

    if (abs(a(1, 1)) < tiny_val) write (error_unit, '(a)') 'scale: leading value is ~zero'
    deallocate (work)
  end subroutine scale
end module scaling
```

### Python

**Types and interfaces**

- Public functions annotated; `mypy`/Pylance clean on changed files; validation performed at I/O boundaries (files, CLI, network) rather than deep in the logic
- No mutable default arguments (`def f(x, acc=[])`); use `None` plus `if acc is None`
- Dataclasses/`NamedTuple`/`attrs` instead of loosely-keyed dicts passed across modules
- No `except:` or `except Exception: pass`; catch the narrow type and `raise ... from exc` with context; no `assert` for validation that must run under `-O`

**Resources and imports**

- Files, sockets, HDF5/NetCDF handles, and temp dirs opened via `with`/context managers; no reliance on GC timing
- No `import *`, no heavy work or network calls at import time, no circular imports papered over with function-level imports unless documented

**Numerics (NumPy/xarray and friends)**

- Vectorized operations, not Python loops over array elements; dtype and precision explicit (`np.float64` vs `float32`); no silent integer overflow or truncation on assignment
- View-vs-copy discipline: `out=` or explicit `.copy()` when mutating shared arrays; broadcasting shapes asserted rather than assumed
- Randomness seeded and recorded; `==` on floats replaced by `math.isclose`/`np.testing.assert_allclose`; unit conversions and physical constants centralized, not inline

**Security**

- No `eval`/`exec`; no `pickle.loads` or unsafe `torch.load` on untrusted data; `yaml.safe_load` not `yaml.load`; `shell=False` with argument lists for `subprocess`
- Secrets from environment or a credentials service, never literals; paths from user input normalized and confined (`pathlib` plus a base-directory check)

#### Examples

```python
# ❌ BAD: mutable default, unsafe YAML, bare except, unmanaged file, swallowed failure
def load_profiles(paths, results=[]):
    for p in paths:
        f = open(p)
        try:
            results.append(np.array(yaml.load(f)))
        except:
            print("failed")
    return results


# ✅ GOOD: typed, safe loader, context manager, explicit errors
def load_profiles(
    paths: Sequence[Path], *, dtype: np.dtype = np.float64
) -> list[np.ndarray]:
    profiles: list[np.ndarray] = []
    for path in paths:
        try:
            with path.open() as fh:
                raw = yaml.safe_load(fh)
        except OSError as exc:
            raise ProfileReadError(str(path)) from exc
        if raw is None:
            raise ValueError(f"{path}: empty or invalid YAML document")
        profiles.append(np.asarray(raw, dtype=dtype))
    return profiles
```

```python
# ❌ BAD: nested Python loops over array elements
def scale(arr, factor):
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            arr[i, j] = arr[i, j] * factor
    return arr


# ✅ GOOD: vectorized, no in-place surprise on a caller's view
def scale(arr: np.ndarray, factor: float) -> np.ndarray:
    return arr * factor
```

### Bash

**Script preamble and safety**

- Interpreter declared explicitly (`#!/usr/bin/env bash` for bash-only scripts, `#!/bin/sh` only when the body is genuinely POSIX); never run a bash script with `sh script.sh`
- `set -euo pipefail` at the top of every non-trivial script, plus `unset CDPATH` when `cd` is used and `LC_ALL=C` when output is parsed. Review that `set -e` is not defeated by `|| true`, by functions whose failure is silently tolerated, or by `if cmd; then` where the exit status matters
- Cleanup via `trap cleanup EXIT` (and `INT TERM` for scripts that spawn processes); the variable the trap reads must be declared at **script scope**, not `local` inside a function, or the trap fires after it goes out of scope and `set -u` aborts the cleanup. Background work is tracked in a PID array and `wait`ed on with status checked
- Functions declare `local`/`declare` for every variable; scripts are sourceable for testing via the `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi` guard

**Quoting, expansion, and control flow**

- Every expansion double-quoted: `"${var}"`, `"$@"`, `"${arr[@]}"`; `$*` and bare `$@` in assignments flagged
- `[[ ]]` (or `[ ]` under `sh`) with correct operator types — `-eq` for integers, `==` for strings; no `[` with `&&`/`||` inside; no unquoted glob-expansion risk on paths built from variables
- No parsing of `ls`; use globs or `find -print0 | while IFS= read -r -d '' f`. Filenames from users or job output treated as untrusted (leading `-` handled with `--`)
- Command substitution exit status preserved: `out=$(cmd) || die "cmd failed: $?"` rather than letting a failure yield an empty value that propagates
- Arithmetic via `(( ))`/`$(( ))` consistently; no `expr`; no string comparison used for versions or numbers
- `cd` always guarded (`cd -- "$dir" || die …`), no reliance on the caller's working directory, and paths derived from `$(dirname -- "${BASH_SOURCE[0]}")` rather than `$0`

**Inputs, portability, and security**

- Options parsed with `getopts` or a `while case` loop, long forms terminated by `--`, with `-h/--help` plus a usage function that exits `0` on request and non-zero on error; unknown options must not be ignored
- External tools verified with `command -v tool || die`; GNU-vs-BSD differences reviewed (`sed -i`, `date -d`/`-v`, `readlink -f`, `stat -c`/`-f`, `timeout`) when macOS or older systems are in scope
- No `eval` on untrusted or interpolated input; no `source`/`.` of a path built from user data; no `curl … | bash`; no `echo` of secrets and no `set -x` in code paths that log credentials or tokens
- Temp files/dirs only via `mktemp` (never `/tmp/name` guesses); output paths created with `mkdir -p` before writing; no writes into shared scratch without an ownership check

**HPC job scripts (Slurm/PBS)**

- Directives use the scheduler's own prefix (`#SBATCH` vs `#PBS`) consistently, and requested resources match what the script launches: `--ntasks`/`-n` vs the `srun`/`mpirun` count, `--cpus-per-task` vs `OMP_NUM_THREADS`, `--mem` vs measured use, `--time` vs the workload
- `module purge` before `module load`; the loaded compiler/MPI stack matches the one used to build the binary, and versions are pinned rather than floating to a default
- Scheduler environment used instead of hardcoded values (`$SLURM_JOB_ID`, `$SLURM_NTASKS`, `$SLURM_SUBMIT_DIR`, `$PBS_JOBID`, `$PBS_O_WORKDIR`); array tasks derive inputs from `%I`/`$PBS_ARRAY_INDEX` with the index range validated against the input list
- The application's exit status is captured and propagated so a failed rank does not report `COMPLETED`; stdout/stderr routed to per-job files (`%j`) to avoid interleaving on shared filesystems; staging in/out of scratch reviewed for cleanup and for collisions between array tasks

#### Examples

```bash
#!/bin/sh
# ❌ BAD: no safety flags, unquoted expansion, parsed ls, swallowed failure, unsafe temp
tmp=/tmp/myscript.$$
for f in `ls $dataDir/*.dat`; do
  echo processing $f
  grep "ERROR" $f >> $tmp || true
done
results=$(run_analysis $1)
eval "rm -rf $outdir"
```

```bash
#!/usr/bin/env bash
# ✅ GOOD: strict mode, quoted expansions, safe iteration, checked status, mktemp + trap
set -euo pipefail
unset CDPATH

usage() { printf 'usage: %s DIR OUTDIR\n' "$0" >&2; }

tmp_file=""                       # script scope so the EXIT trap can always see it
cleanup() {
  if [[ -n $tmp_file ]]; then rm -f -- "$tmp_file"; fi
}
trap cleanup EXIT INT TERM

main() {
  [[ $# -eq 2 ]] || { usage; exit 2; }
  local -r data_dir=$1 out_dir=$2

  command -v run_analysis >/dev/null || { echo "run_analysis not on PATH" >&2; exit 127; }
  [[ -d $data_dir ]] || { echo "no such directory: $data_dir" >&2; exit 1; }
  mkdir -p -- "$out_dir"

  tmp_file=$(mktemp) || exit 1

  local -a files=()
  local f rc results
  while IFS= read -r -d '' f; do files+=("$f"); done \
    < <(find "$data_dir" -maxdepth 1 -type f -name '*.dat' -print0 | sort -z)

  (( ${#files[@]} > 0 )) || { echo "no input files in $data_dir" >&2; exit 1; }

  for f in "${files[@]}"; do
    printf 'processing %s\n' "$f" >&2
    rc=0
    grep -c 'ERROR' -- "$f" >"$tmp_file" || rc=$?
    case $rc in
      0|1) : ;;                        # 1 = no matches, which is expected
      *)   echo "grep failed on $f" >&2; return "$rc" ;;
    esac
  done

  results=$(run_analysis -- "$data_dir") || { echo "analysis failed" >&2; return 1; }
  printf '%s\n' "$results" >"$out_dir/summary.txt"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi
```

## Performance Considerations

When performing a code review, check for performance issues:

- **Database Queries**: Avoid N+1 queries, use proper indexing
- **Algorithms**: Appropriate time/space complexity for the use case
- **Caching**: Utilize caching for expensive or repeated operations
- **Resource Management**: Proper cleanup of connections, files, streams
- **Pagination**: Large result sets should be paginated
- **Lazy Loading**: Load data only when needed
- **Memory Access**: Unit-stride and contiguous access, cache-friendly layout, no per-call reallocation in inner loops
- **Allocation in Loops**: No allocation, I/O, or logging inside compute kernels or tight loops
- **Vectorization**: Inner loops free of function calls, aliasing, or early exits that block SIMD; check the compiler vectorization report for hot kernels
- **Parallel Efficiency**: Load balance across ranks/threads, minimal synchronization, communication volume proportional to work, no false sharing
- **I/O**: Collective or per-rank output batched, restarts written on scratch and staged out, no repeated reads of the same input

### Examples
```python
# ❌ BAD: N+1 query problem
users = User.query.all()
for user in users:
    orders = Order.query.filter_by(user_id=user.id).all()  # N+1!

# ✅ GOOD: Use JOIN or eager loading
users = User.query.options(joinedload(User.orders)).all()
for user in users:
    orders = user.orders
```

```c
/* ❌ BAD: allocation and strlen in the inner loop; stride-2 access */
for (int i = 0; i < n; i++) {
    char *tmp = malloc(len);
    for (int j = 0; j < m; j += 2) tmp[j] = in[i * stride + j];
    free(tmp);
}

/* ✅ GOOD: buffer allocated once outside the loop; unit-stride inner loop */
char *tmp = malloc(len);
if (tmp == NULL) return -ENOMEM;
for (int i = 0; i < n; i++) {
    const char *src = &in[(size_t)i * stride];
    memcpy(tmp, src, (size_t)len);       /* vectorized, contiguous copy */
}
free(tmp);
```

```cpp
// ❌ BAD: reallocation per iteration, copying instead of moving
std::vector<Result> results;
for (const auto &sample : samples) {
    std::string key = sample.name();          // copy on every iteration
    results.push_back(compute(std::move(sample)));
}

// ✅ GOOD: reserve once, no per-iteration allocation, move semantics
std::vector<Result> results;
results.reserve(samples.size());
for (const auto &sample : samples) {
    results.emplace_back(compute(sample));
}
```

```fortran
! ❌ BAD: slowest-varying index innermost, temporary allocated per call
do i = 1, n
  do j = 1, m
    a(i, j) = b(i, j) * c(j)
  end do
end do

! ✅ GOOD: unit stride on the leftmost index, array expression, no temporaries
do j = 1, m
  a(:, j) = b(:, j) * c(j)
end do

! For a reduction, pin the inner index and let the compiler vectorize:
do concurrent (i = 1:n) reduce(+:) s
  s = s + a(i) * b(i)
end do
```

```bash
# ❌ BAD: one process spawn per file, repeated parsing of the same input
for f in $(ls "$dir"); do
  head -n 1 "$dir/$f" | awk '{print $3}'
  head -n 1 "$dir/$f" | awk '{print $4}'
done

# ✅ GOOD: single awk pass, NUL-safe iteration, no subshell per file
find "$dir" -maxdepth 1 -type f -name '*.dat' -print0 |
  xargs -0 -r awk 'FNR == 1 { print $3, $4 }'
```

## Architecture and Design

When performing a code review, verify architectural principles:

- **Separation of Concerns**: Clear boundaries between layers/modules
- **Dependency Direction**: High-level modules don't depend on low-level details
- **Interface Segregation**: Prefer small, focused interfaces
- **Loose Coupling**: Components should be independently testable
- **High Cohesion**: Related functionality grouped together
- **Consistent Patterns**: Follow established patterns in the codebase

## Documentation Standards

When performing a code review, check documentation:

- **API Documentation**: Public APIs must be documented (purpose, parameters, returns)
- **Complex Logic**: Non-obvious logic should have explanatory comments
- **README Updates**: Update README when adding features or changing setup
- **Breaking Changes**: Document any breaking changes clearly
- **Examples**: Provide usage examples for complex features
- **Units and Ranges**: Scientific functions state units, sign conventions, and valid input ranges
- **Build Requirements**: Document the compiler/interpreter versions, required flags, and modules needed to build and test

### Per-Language Documentation Conventions
- **C**: Doxygen-style comments on exported functions in headers; ownership, buffer sizes, and error-return semantics stated for every `extern`
- **C++**: Doc comments on public classes/functions; preconditions, lifetime of returned references/views, and exception guarantees stated
- **Fortran**: `!!` or Doxygen comment blocks on module procedures; dummy-argument intent, shape, and units documented where `intent`/assumed-shape cannot express them
- **Python**: Docstrings in the project's convention (NumPy or Google style) on public API; type hints kept in sync with the prose
- **Bash**: Header comment with purpose, usage, options, and required external tools; `usage()` output kept current with the parser

## Comment Format Template

When performing a code review, use this format for comments:

```markdown
**[PRIORITY] Category: Brief title**

Detailed description of the issue or suggestion.

**Why this matters:**
Explanation of the impact or reason for the suggestion.

**Suggested fix:**
[code example if applicable]

**Reference:** [link to relevant documentation or standard]
```

### Example Comments

#### Critical Issue
````markdown
**🔴 CRITICAL - Security: SQL Injection Vulnerability**

The query on line 45 concatenates user input directly into the SQL string,
creating a SQL injection vulnerability.

**Why this matters:**
An attacker could manipulate the email parameter to execute arbitrary SQL commands,
potentially exposing or deleting all database data.

**Suggested fix:**
```sql
-- Instead of:
query = "SELECT * FROM users WHERE email = '" + email + "'"

-- Use:
PreparedStatement stmt = conn.prepareStatement(
    "SELECT * FROM users WHERE email = ?"
);
stmt.setString(1, email);
```

**Reference:** OWASP SQL Injection Prevention Cheat Sheet
````

#### Critical Issue (C/C++ memory safety)
````markdown
**🔴 CRITICAL - Correctness: Use-after-free in the error path**

`parse_header()` frees `buf` at line 88 but `hdr->name` still points into it, so the
`strcmp` at line 94 reads freed memory. This is undefined behaviour and will pass under
`-O2` in CI and crash in production.

**Why this matters:**
Use-after-free is exploitable and non-deterministic, so it will not reproduce reliably in
testing. AddressSanitizer would flag it immediately.

**Suggested fix:**
```c
/* Instead of: */
free(buf);
if (strcmp(hdr->name, "restart") == 0) { ... }

/* Copy what you need before releasing the source buffer: */
char name[HEADER_NAME_MAX];
snprintf(name, sizeof name, "%s", hdr->name);
free(buf);
buf = NULL;
if (strcmp(name, "restart") == 0) { ... }
```

**Reference:** CERT C MEM03-C: Never access freed memory
````

#### Critical Issue (Fortran numerics)
````markdown
**🔴 CRITICAL - Correctness: Exact floating-point comparison in the convergence check**

Line 210 tests `if (residual == 0.0)` to detect convergence. A residual computed in
`real(real64)` will essentially never be exactly zero, so the loop always runs to
`max_iter` and the solver silently reports non-convergence.

**Why this matters:**
Floating-point equality is unreliable, and with `-ffast-math` or a different reduction
order the result changes between runs, breaking reproducibility across rank counts.

**Suggested fix:**
```fortran
! Instead of:
if (residual == 0.0) exit

! Use a documented tolerance and guard against NaN:
if (residual /= residual) then
  write (error_unit, '(a)') 'solve: residual is NaN'
  stop 1
end if
if (residual <= tol) exit
```

**Reference:** ISO/IEC 10967 (Language-Independent Numerics); NAG Fortran `-C=fp` checks
````

#### Important Issue
````markdown
**🟡 IMPORTANT - Testing: Missing test coverage for critical path**

The `processPayment()` function handles financial transactions but has no tests
for the refund scenario.

**Why this matters:**
Refunds involve money movement and should be thoroughly tested to prevent
financial errors or data inconsistencies.

**Suggested fix:**
Add test case:
```javascript
test('should process full refund when order is cancelled', () => {
    const order = createOrder({ total: 100, status: 'cancelled' });

    const result = processPayment(order, { type: 'refund' });

    expect(result.refundAmount).toBe(100);
    expect(result.status).toBe('refunded');
});
```
````

#### Important Issue (HPC/Bash)
````markdown
**🟡 IMPORTANT - Testing: Job script requests resources it does not use**

`run_solver.sh` requests `--ntasks=64` and `--cpus-per-task=8`, but launches with
`srun -n 16 ./solver` and never sets `OMP_NUM_THREADS`, so 48 ranks worth of paid
allocation stay idle and OpenMP oversubscribes the node.

**Why this matters:**
Mismatched requests either waste queued capacity on shared systems or cause thread
oversubscription that makes the run slower than a serial build, and the job will not
reproduce on a system with a different tasks-per-node layout.

**Suggested fix:**
```bash
#SBATCH --ntasks=16
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:?set by Slurm}"
export OMP_PLACES=cores
export OMP_PROC_BIND=close

srun --ntasks="${SLURM_NTASKS}" --cpus-per-task="${SLURM_CPUS_PER_TASK}" \
  ./solver --input "${input_file}" --output "${output_file}"
status=$?
exit "$status"
```

**Reference:** Slurm documentation on `--cpus-per-task` and OpenMP binding
````

#### Suggestion
````markdown
**🟢 SUGGESTION - Readability: Simplify nested conditionals**

The nested if statements on lines 30-40 make the logic hard to follow.

**Why this matters:**
Simpler code is easier to maintain, debug, and test.

**Suggested fix:**
```javascript
// Instead of nested ifs:
if (user) {
    if (user.isActive) {
        if (user.hasPermission('write')) {
            // do something
        }
    }
}

// Consider guard clauses:
if (!user || !user.isActive || !user.hasPermission('write')) {
    return;
}
// do something
```
````

#### Suggestion (C++/Python)
````markdown
**🟢 SUGGESTION - Readability: Prefer early exits over deep nesting**

Lines 55-80 nest three levels of `if` around the write, so the failure paths and the
success path are hard to tell apart.

**Why this matters:**
Guard clauses make the normal path obvious and keep each error condition testable on
its own.

**Suggested fix:**
```cpp
// Instead of nesting the whole body:
if (handle) { if (handle->is_open()) { if (can_write(handle)) { write(handle); } } }

// Use guard clauses:
if (!handle || !handle->is_open()) {
    throw InvalidHandleError("output handle is not open");
}
if (!CanWrite(*handle)) {
    throw PermissionError("handle is not writable");
}
Write(*handle);
```

```python
# Same idea in Python:
if handle is None or not handle.open:
    raise InvalidHandleError("output handle is not open")
if not can_write(handle):
    raise PermissionError("handle is not writable")
write(handle)
```
````

## Operational Compliance (NCO EE2)

When the target is WCOSS or an NCO delivery, apply the NCO Environmental Equivalence
(EE2) standards through the `ee2-standards` skill and its per-file review checklists.

- **EE2 overrides style preferences.** Where a formatting or structural choice conflicts
  with an EE2 rule — message prefixes, restart, cleanup, module-driven builds, branch
  naming — EE2 wins for operational code.
- **Scope the advice.** EE2 rules tagged **[WCOSS]** (`$COMOUT`, `prep_step`, PBS
  directives, `dbn_alert`) do not apply to RDHPCS, workstation, or research-only code.
  Applying them there produces actively wrong advice. Review those targets against the
  **[portable]** subset only, and say so.

## Review Checklist

When performing a code review, systematically verify:

### Code Quality
- [ ] Code follows consistent style and conventions
- [ ] Names are descriptive and follow naming conventions
- [ ] Functions/methods are small and focused
- [ ] No code duplication
- [ ] Complex logic is broken into simpler parts
- [ ] Error handling is appropriate
- [ ] No commented-out code or TODO without tickets
- [ ] Failure paths report on `stderr`/`error_unit` and propagate a non-zero exit status or error code

### Security
- [ ] No sensitive data in code or logs
- [ ] Input validation on all user inputs
- [ ] No SQL injection vulnerabilities
- [ ] No command injection (`system()`, `eval`, `shell=True`) or unsafe deserialization (`pickle`, `yaml.load`, unsigned weights)
- [ ] No unbounded copies or input-derived format strings in C/C++/Fortran
- [ ] Authentication and authorization properly implemented
- [ ] Dependencies are up-to-date and secure

### Testing
- [ ] New code has appropriate test coverage
- [ ] Tests are well-named and focused
- [ ] Tests cover edge cases and error scenarios
- [ ] Tests are independent and deterministic
- [ ] No tests that always pass or are commented out
- [ ] Float comparisons use a documented tolerance or a bit-reproducible baseline
- [ ] Parallel/accelerator builds tested against the serial result

### Language-Specific
- [ ] **C**: allocations checked and freed on every path; bounded string APIs; no undefined behaviour; `-Wall -Wextra -Werror`
- [ ] **C++**: RAII with no owning raw `new`/`delete`; no dangling views; `const`/`noexcept`/`override`; thread-safe shared state
- [ ] **Fortran**: `implicit none`, modules instead of `COMMON`, kind parameters, `intent`, checked `allocate`, unit-stride loops, tolerance comparisons
- [ ] **Python**: annotations and static checks clean, no mutable defaults, no bare `except`, context managers, vectorized numerics, no unsafe deserialization
- [ ] **Bash**: `set -euo pipefail`, quoted expansions, `mktemp` + `trap` cleanup, no `ls` parsing or `eval`, `shellcheck` clean; job-script directives consistent with resources actually used
- [ ] Compiler/interpreter versions and flags used by the PR match the project's supported matrix
- [ ] Debug/test build includes bounds, uninitialized-use, and floating-point exception checking
- [ ] Optimized build flags (`-ffast-math`, `-Ofast`, `-march=`) reviewed for numerical impact

### Performance
- [ ] No obvious performance issues (N+1, memory leaks)
- [ ] Appropriate use of caching
- [ ] Efficient algorithms and data structures
- [ ] Proper resource cleanup
- [ ] Inner loops use unit stride / contiguous access and avoid allocation, I/O, or logging
- [ ] Vectorization and OpenMP/OpenACC regions reviewed for independence and reduction correctness
- [ ] Communication volume and load balance reviewed for MPI/threaded runs

### Architecture
- [ ] Follows established patterns and conventions
- [ ] Proper separation of concerns
- [ ] No architectural violations
- [ ] Dependencies flow in correct direction

### Documentation
- [ ] Public APIs are documented
- [ ] Complex logic has explanatory comments
- [ ] README is updated if needed
- [ ] Breaking changes are documented

## Project-Specific Customizations

To customize this template for your project, add sections for:

1. **Language/Framework specific checks**
   - Example: "When performing a code review, verify React hooks follow rules of hooks"
   - Example: "When performing a code review, check Spring Boot controllers use proper annotations"
   - Example: "When performing a code review, verify Fortran kernels declare `intent` and use `real(real64)` kinds from `iso_fortran_env`"
   - Example: "When performing a code review, check C++ interfaces take `std::span`/`std::string_view` rather than raw pointer-plus-length pairs"
   - Example: "When performing a code review, verify Python drivers keep array dtype and unit conversions in one module, not inline"
   - Example: "When performing a code review, check Bash scripts use `set -euo pipefail` and quote every expansion"

2. **Build and deployment**
   - Example: "When performing a code review, verify CI/CD pipeline configuration is correct"
   - Example: "When performing a code review, check database migrations are reversible"
   - Example: "When performing a code review, verify the CMake/Meson/fpm target list covers new sources and that out-of-tree builds are tested"
   - Example: "When performing a code review, check compiler and module versions are pinned in the build and match the CI matrix"
   - Example: "When performing a code review, verify optimized builds do not add `-ffast-math`/`-Ofast` without a recorded tolerance comparison"

3. **Business logic rules**
   - Example: "When performing a code review, verify pricing calculations include all applicable taxes"
   - Example: "When performing a code review, check user consent is obtained before data processing"
   - Example: "When performing a code review, verify physical constants and unit conversions come from the shared constants module"
   - Example: "When performing a code review, check diagnostic and restart output retains enough metadata to reproduce the run"

4. **Team conventions**
   - Example: "When performing a code review, verify commit messages follow conventional commits format"
   - Example: "When performing a code review, check branch names follow pattern: type/ticket-description"

5. **Per-language instruction files (optional)**
   - For language standards that apply only to certain files, split them into sibling instruction files with `applyTo` globs instead of growing this template: `**/*.c, **/*.h`, `**/*.cc, **/*.hpp`, `**/*.f90, **/*.F90`, `**/*.py`, `**/*.sh`

## Additional Resources

For more information on effective code reviews and GitHub Copilot customization:

- [GitHub Copilot Prompt Engineering](https://docs.github.com/en/copilot/concepts/prompting/prompt-engineering)
- [GitHub Copilot Custom Instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)
- [Awesome GitHub Copilot Repository](https://github.com/github/awesome-copilot)
- [GitHub Code Review Guidelines](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests)
- [Google Engineering Practices - Code Review](https://google.github.io/eng-practices/review/)
- [OWASP Security Guidelines](https://owasp.org/)

Language and tooling references:

- **C**: [CERT C Secure Coding Standard](https://wiki.sei.cmu.edu/confluence/display/c/sei+secure+coding+standards), [Cppcheck](https://cppcheck.sourceforge.io/), [AddressSanitizer/UBSan](https://clang.llvm.org/docs/AddressSanitizer.html)
- **C++**: [C++ Core Guidelines](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines), [clang-tidy checks](https://clang.tidy.org/checks.html), [GoogleTest](https://google.github.io/googletest/), [Catch2](https://github.com/catchorg/Catch2)
- **Fortran**: [Metacode Fortran Style Guide](https://metacode.biz/Fortran/StyleGuide), [Modern Fortran](https://modern-fortran.org), [fpm](https://fortran-lang.org/learn/fpm/), [pFUnit](https://github.com/Goddard-Fortran-Ecosystem/pFUnit)
- **Python**: [pytest](https://docs.pytest.org/), [NumPy testing guide](https://numpy.org/doc/stable/reference/routines.testing.html), [Hypothesis](https://hypothesis.readthedocs.io/), [ruff](https://docs.astral.sh/ruff/), [mypy](https://mypy-lang.org/)
- **Bash**: [Google Shell Style Guide](https://google.github.io/styleguide/shellguide.html), [ShellCheck](https://www.shellcheck.net/), [bats-core](https://github.com/bats-core/bats-core), [Bash Guide for Hardcore Users](https://mywiki.wooledge.org/BashGuide)
- **HPC**: [Slurm documentation](https://slurm.schedmd.com/), [PBS Pro User's Guide](https://www.altair.com/pbs-professional/), [MPICH debugging guide](https://www.mpich.org/static/downloads/)

## Prompt Engineering Tips

When performing a code review, apply these prompt engineering principles from the [GitHub Copilot documentation](https://docs.github.com/en/copilot/concepts/prompting/prompt-engineering):

1. **Start General, Then Get Specific**: Begin with high-level architecture review, then drill into implementation details
2. **Give Examples**: Reference similar patterns in the codebase when suggesting changes
3. **Break Complex Tasks**: Review large PRs in logical chunks (security → tests → logic → style)
4. **Avoid Ambiguity**: Be specific about which file, line, and issue you're addressing
5. **Indicate Relevant Code**: Reference related code that might be affected by changes
6. **Experiment and Iterate**: If initial review misses something, review again with focused questions

## Project Context

This is a generic template. Customize this section with your project-specific information:

- **Tech Stack**: [e.g., Fortran 2018 + C++20 + Python 3.11, or C17 with MPI/OpenMP]
- **Architecture**: [e.g., Hexagonal/Clean Architecture, Microservices, HPC kernel + Python driver]
- **Build Tool**: [e.g., CMake, Meson, Make, fpm, pip/conda, Spack]
- **Testing**: [e.g., pytest, GoogleTest/Catch2 + CTest, Unity, pFUnit or `fpm test`, bats-core]
- **Code Style**: [e.g., Google Style Guide, clang-format, ruff/black, fprettify, `shfmt` + `shellcheck`]
- **Compilers**: [e.g., GCC 14, Clang 19, ifx, NAG — and which are CI-gated]
- **Shell**: [e.g., bash 5 with `set -euo pipefail`; scripts linted with `shellcheck` in CI]

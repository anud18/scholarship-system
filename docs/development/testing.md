# Testing Guide

This document outlines the testing strategy and procedures for the Scholarship Management System frontend.

## Testing Stack

- **Unit Testing**: Jest + React Testing Library
- **E2E Testing**: Playwright
- **Component Testing**: React Testing Library with mocked hooks
- **API Testing**: Jest with mocked fetch requests

## Test Structure

```
frontend/
├── __tests__/                  # Global tests
├── lib/__tests__/             # API client tests
├── hooks/__tests__/           # Custom hooks tests
├── components/__tests__/      # Component tests
├── e2e/                       # End-to-end tests
│   ├── auth.spec.ts          # Authentication flow tests
│   ├── student-workflow.spec.ts # Student application workflow
│   └── admin-dashboard.spec.ts # Admin functionality tests
├── jest.config.js            # Jest configuration
└── playwright.config.ts      # Playwright configuration
```

## Running Tests

### Unit Tests

```bash
# Run all unit tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Run specific test file
npm test lib/__tests__/api.test.ts
```

### End-to-End Tests

```bash
# Run all E2E tests (requires frontend to be running)
npm run test:e2e

# Run E2E tests with UI mode
npm run test:e2e:ui

# Run specific E2E test
npx playwright test e2e/auth.spec.ts
```

## Test Coverage Requirements

- **Minimum Coverage**: 70% across all metrics
- **Target Coverage**: 80%+ for critical paths
- **Required Coverage**:
  - API client: 90%+
  - Authentication: 95%+
  - Application workflow: 85%+

## Test Categories

### 1. Unit Tests

#### API Client Tests (`lib/__tests__/api.test.ts`)
- Authentication endpoints
- Application CRUD operations
- Error handling
- Token management

#### Hook Tests (`hooks/__tests__/use-auth.test.tsx`)
- Authentication state management
- User profile updates
- Error states
- Loading states

#### Component Tests (`components/__tests__/enhanced-student-portal.test.tsx`)
- Component rendering
- User interactions
- Form validation
- State changes
- Language switching

### 2. End-to-End Tests

#### Authentication Flow (`e2e/auth.spec.ts`)
- Login with valid credentials
- Login failure handling
- Role-based redirects
- Logout functionality

#### Student Workflow (`e2e/student-workflow.spec.ts`)
- Application creation
- Form validation
- Progress tracking
- Application management
- Language switching
- Status updates

#### Admin Dashboard (`e2e/admin-dashboard.spec.ts`)
- Dashboard statistics
- Application management
- User management
- Scholarship management
- Export functionality

## Test Data and Mocking

### API Mocking Strategy

Tests use different mocking approaches:

1. **Unit Tests**: Mock individual functions and modules
2. **E2E Tests**: Mock entire API responses using Playwright route interceptors

### Mock Data Examples

```typescript
// User mock data
const mockUser = {
  id: '1',
  username: 'testuser',
  email: 'test@example.com',
  role: 'student',
  full_name: 'Test User',
  is_active: true,
  created_at: '2025-01-01',
  updated_at: '2025-01-01'
}

// Application mock data
const mockApplication = {
  id: 1,
  student_id: 'student1',
  scholarship_type: 'academic_excellence',
  status: 'submitted',
  personal_statement: 'Test statement',
  gpa_requirement_met: true,
  created_at: '2025-01-01',
  updated_at: '2025-01-01'
}
```

## Testing Best Practices

### 1. Test Naming Convention

```typescript
describe('ComponentName', () => {
  it('should do something when condition is met', () => {
    // Test implementation
  })
})
```

### 2. Test Organization

- Group related tests using `describe` blocks
- Use `beforeEach` for common setup
- Clean up mocks after each test
- Use meaningful test descriptions

### 3. Assertions

```typescript
// Good - specific and clear
expect(screen.getByText('Login successful')).toBeVisible()
expect(mockFunction).toHaveBeenCalledWith(expectedParams)

// Avoid - too generic
expect(element).toBeTruthy()
```

### 4. Mock Management

```typescript
// Reset mocks before each test
beforeEach(() => {
  jest.clearAllMocks()
})

// Mock specific implementations
mockApiClient.auth.login.mockResolvedValueOnce({
  success: true,
  data: { access_token: 'token' }
})
```

## Debugging Tests

### Jest Debugging

```bash
# Run tests with debug output
npm test -- --verbose

# Run specific test with debugging
node --inspect-brk node_modules/.bin/jest lib/__tests__/api.test.ts
```

### Playwright Debugging

```bash
# Run with headed browser
npx playwright test --headed

# Debug specific test
npx playwright test e2e/auth.spec.ts --debug

# Generate test report
npx playwright show-report
```

## Continuous Integration

### GitHub Actions Configuration

```yaml
name: Frontend Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: npm install
      - run: npm test -- --coverage
      - run: npx playwright install
      - run: npm run test:e2e
```

## Performance Testing

### Load Testing Considerations

- Test component rendering performance
- Monitor memory leaks in tests
- Verify async operation timing
- Test with large datasets

### Metrics to Monitor

- Test execution time
- Memory usage during tests
- API response times in E2E tests
- Bundle size impact

## Troubleshooting

### Common Issues

1. **Mock Issues**
   ```bash
   # Clear Jest cache
   npx jest --clearCache
   ```

2. **Playwright Browser Issues**
   ```bash
   # Reinstall browsers
   npx playwright install
   ```

3. **Import Path Issues**
   - Use relative imports in tests
   - Check tsconfig.json paths configuration

4. **Async Test Issues**
   - Always await async operations
   - Use `waitFor` for React Testing Library
   - Use `expect().resolves` for promises

### Test Environment Issues

If tests fail due to environment:

1. Check Node.js version (18+)
2. Verify all dependencies installed
3. Ensure backend is running for E2E tests
4. Check port availability (3000 for frontend)

## Future Enhancements

### Planned Improvements

1. **Visual Regression Testing**
   - Add screenshot comparison tests
   - Test responsive design

2. **Accessibility Testing**
   - Add axe-core integration
   - Test keyboard navigation

3. **Performance Testing**
   - Add Lighthouse CI
   - Memory leak detection

4. **Integration Testing**
   - Add backend integration tests
   - Database integration testing

### Test Maintenance

- Review and update tests monthly
- Remove obsolete tests
- Update mock data to match API changes
- Monitor test execution times
- Regularly update testing dependencies 
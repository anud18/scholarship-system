/**
 * Centralized logging utility with environment-aware behavior
 *
 * SECURITY: In production, logs generic messages only to prevent information leakage
 * In development, logs detailed error information for debugging
 *
 * Usage:
 *   import { logger } from '@/lib/utils/logger';
 *   logger.error('Failed to fetch data', { error, context });
 *   logger.warn('Deprecated API used', { endpoint });
 *   logger.info('User logged in', { userId });
 */

type LogLevel = 'error' | 'warn' | 'info' | 'debug';

interface LogContext {
  [key: string]: unknown;
}

class Logger {
  private isDevelopment: boolean;

  constructor() {
    this.isDevelopment = process.env.NODE_ENV === 'development';
  }

  /**
   * Log error messages
   * Production: Generic message only
   * Development: Full details
   */
  error(message: string, context?: LogContext): void {
    if (this.isDevelopment) {
      console.error(`[ERROR] ${message}`, context || '');
    } else {
      // Production: Log to external service (future implementation)
      // For now, silently fail to prevent information leakage
      this.sendToExternalLogger('error', message, context);
    }
  }

  /**
   * Log warning messages
   * Production: Generic message only
   * Development: Full details
   */
  warn(message: string, context?: LogContext): void {
    if (this.isDevelopment) {
      console.warn(`[WARN] ${message}`, context || '');
    } else {
      this.sendToExternalLogger('warn', message, context);
    }
  }

  /**
   * Log informational messages
   * Production: Silent
   * Development: Full details
   */
  info(message: string, context?: LogContext): void {
    if (this.isDevelopment) {
      console.info(`[INFO] ${message}`, context || '');
    }
  }

  /**
   * Log debug messages (development only)
   */
  debug(message: string, context?: LogContext): void {
    if (this.isDevelopment) {
      console.debug(`[DEBUG] ${message}`, context || '');
    }
  }

  /**
   * Send logs to external logging service (future implementation)
   * This could send to backend API, Sentry, LogRocket, etc.
   */
  private sendToExternalLogger(
    level: LogLevel,
    message: string,
    context?: LogContext
  ): void {
    // Future: Send to backend logging endpoint
    // fetch('/api/v1/logs', {
    //   method: 'POST',
    //   body: JSON.stringify({ level, message, context, timestamp: new Date() })
    // });

    // For now, do nothing to prevent information leakage in production
  }
}

// Export singleton instance
export const logger = new Logger();

// Export type for use in other files
export type { LogContext };

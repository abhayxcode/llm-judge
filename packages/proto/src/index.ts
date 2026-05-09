/**
 * Shared types between web, sdk-ts, and any TS consumer.
 *
 * M1 skeleton: empty. Schema lands when CH/PG schemas land.
 */

export type ULID = string & { readonly __brand: 'ULID' };
export type ISO8601 = string & { readonly __brand: 'ISO8601' };

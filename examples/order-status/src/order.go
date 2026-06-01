package order

import (
	"errors"
	"time"
)

type Status string

const (
	StatusPending   Status = "PENDING"
	StatusConfirmed Status = "CONFIRMED"
	StatusShipped   Status = "SHIPPED"
	StatusDelivered Status = "DELIVERED"
	StatusCancelled Status = "CANCELLED"
)

var ErrInvalidTransition = errors.New("INVALID_TRANSITION")

type AuditEntry struct {
	From      Status
	To        Status
	Actor     string
	Timestamp time.Time
}

type Order struct {
	ID          string
	Status      Status
	AuditLog    []AuditEntry
	DeliveredAt *time.Time
}

var allowedTransitions = map[Status][]Status{
	StatusPending:   {StatusConfirmed, StatusCancelled},
	StatusConfirmed: {StatusShipped, StatusCancelled},
	StatusShipped:   {StatusDelivered},
}

func (o *Order) Transition(to Status, actor string, now time.Time) error {
	if o.Status == to {
		// Idempotent: already in target state
		return nil
	}

	allowed := allowedTransitions[o.Status]
	valid := false
	for _, s := range allowed {
		if s == to {
			valid = true
			break
		}
	}
	if !valid {
		return ErrInvalidTransition
	}

	o.AuditLog = append(o.AuditLog, AuditEntry{
		From:      o.Status,
		To:        to,
		Actor:     actor,
		Timestamp: now,
	})
	o.Status = to

	if to == StatusDelivered {
		o.DeliveredAt = &now
	}
	return nil
}

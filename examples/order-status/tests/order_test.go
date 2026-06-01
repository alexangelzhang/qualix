package order_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	order "example/order-status/src"
)

func newOrder() *order.Order {
	return &order.Order{ID: "ord-1", Status: order.StatusPending}
}

func TestTransition_ValidPath(t *testing.T) {
	o := newOrder()
	now := time.Now()
	err := o.Transition(order.StatusConfirmed, "operator", now)
	require.NoError(t, err)
	assert.Equal(t, order.StatusConfirmed, o.Status)
}

func TestTransition_AuditLogGrows(t *testing.T) {
	o := newOrder()
	now := time.Now()
	o.Transition(order.StatusConfirmed, "op", now)
	assert.Len(t, o.AuditLog, 1)
}

func TestTransition_DeliveredSetsTimestamp(t *testing.T) {
	o := newOrder()
	now := time.Now()
	o.Transition(order.StatusConfirmed, "op", now)
	o.Transition(order.StatusShipped, "op", now)
	o.Transition(order.StatusDelivered, "op", now)
	assert.NotNil(t, o.DeliveredAt)
}

// Missing: test that an illegal transition returns ErrInvalidTransition and does NOT modify status
// Missing: test that CANCELLED -> CONFIRMED is rejected (cancelled is terminal)
// Missing: test that repeating the same transition is idempotent (no second audit entry)
// Missing: test that audit log length is exactly 1 after one transition (not 0, not 2)

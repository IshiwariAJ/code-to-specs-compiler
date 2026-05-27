// Package main is a kitchen sink Go sample.
// Purpose: compile supported constructs and expose unsupported constructs as warnings.
package main

import (
	"errors"
	"fmt"
)

const MaxPoints = 1000
const PremiumThreshold = 100000

var auditCounter = 0

type Purchase struct {
	Price    int
	Category string
}

type User struct {
	ID              string
	Status          string
	Rank            string
	PurchaseHistory []Purchase
	Metadata        map[string]string
}

type BenefitResult struct {
	Points  int
	Message string
	Level   string
}

type Notifier interface {
	Notify(message string) error
}

// calculateUserBenefit is the supported-heavy function.
func calculateUserBenefit(user User, dryRun bool, tags ...string) (BenefitResult, error) {
	if user.Status != "ACTIVE" {
		return BenefitResult{}, errors.New("inactive user")
	}

	totalAmount := 0
	for _, history := range user.PurchaseHistory {
		totalAmount += history.Price
	}

	for i := 0; i < len(tags); i++ {
		fmt.Println(tags[i])
	}

	defer fmt.Println("benefit calculation finished")

	if dryRun {
		return BenefitResult{Points: 0, Message: "dry run", Level: "basic"}, nil
	} else if totalAmount >= PremiumThreshold && user.Rank == "Gold" {
		return BenefitResult{Points: MaxPoints, Message: "premium benefit", Level: "premium"}, nil
	} else if totalAmount >= 50000 {
		return BenefitResult{Points: 500, Message: "standard benefit", Level: "standard"}, nil
	} else {
		return BenefitResult{Points: 100, Message: "basic benefit", Level: "basic"}, nil
	}
}

// inspectUnsupportedFlow includes unsupported control-flow forms for warning checks.
func inspectUnsupportedFlow(user User, values []int, ch chan int) int {
	index := 0
	total := 0

	for index < len(values) {
		total += values[index]
		index++
	}

	switch user.Status {
	case "ACTIVE":
		total += 10
	case "BANNED":
		total -= 100
	default:
		total += 0
	}

	select {
	case value := <-ch:
		total += value
	default:
		total += 0
	}

	go func() {
		fmt.Println("background audit")
	}()

	func(label string) {
		fmt.Println(label)
	}("anonymous function")

	for key, value := range user.Metadata {
		fmt.Println(key, value)
	}

	return total
}

func recoverableWork() {
	defer func() {
		if err := recover(); err != nil {
			fmt.Println(err)
		}
	}()
	panic("boom")
}


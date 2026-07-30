using UnityEngine;

public class Figure8Controller : MonoBehaviour
{
    [Header("Trajectory Parameters")]
    public float speed = 0.5f;
    public float radius = 2.0f;
    public float height = 2.5f; // Keep your new height

    [Header("APF Gains (Tune these)")]
    public float attractiveGain = 4.0f;  // Pull strength to trajectory
    public float repulsiveGain = 12.0f;  // Max push strength away from user
    public float dampingGain = 1.5f;     // "Braking" force (Crucial for stopping the hit)

    [Header("Avoidance Settings")]
    public Transform userHead;
    public float avoidanceRadius = 3.0f; // INCREASED: Start reacting at 3 meters!
    public float safetyBuffer = 1.0f;    // Minimum safe distance (force caps here)

    private Rigidbody rb;
    private float time;
    private Vector3 centerOffset;

    void Start()
    {
        rb = GetComponent<Rigidbody>();
        rb.useGravity = true;
        
        // Add physical damping to the Rigidbody itself for smoother flight
        rb.linearDamping = 0.5f; 
        
        centerOffset = transform.position;
        centerOffset.y = height;
    }

    void FixedUpdate()
    {
        if (userHead == null) return;

        // 1. Calculate Attractive Force (Pull to Figure-8)
        Vector3 attractiveForce = CalculateAttractiveForce();

        // 2. Calculate Repulsive Force (Push away from User)
        Vector3 toUser = userHead.position - transform.position;
        float distanceToUser = toUser.magnitude;
        Vector3 repulsiveForce = CalculateRepulsiveForce(toUser, distanceToUser);

        // 3. Calculate Damping Force (Braking)
        // This opposes the drone's current velocity, preventing it from crashing into you
        Vector3 dampingForce = -rb.linearVelocity * dampingGain;

        // 4. Combine Forces (No hard switching!)
        Vector3 totalForce = attractiveForce + repulsiveForce + dampingForce;

        // Apply Force
        rb.AddForce(totalForce, ForceMode.Force);
    }

    Vector3 CalculateAttractiveForce()
    {
        time += speed * Time.fixedDeltaTime;
        
        // Lemniscate of Gerono (Figure-8)
        float x = radius * Mathf.Sin(time);
        float z = radius * Mathf.Sin(time) * Mathf.Cos(time);
        Vector3 targetPosition = centerOffset + new Vector3(x, 0, z);

        // Proportional control to pull toward the path
        Vector3 positionError = targetPosition - transform.position;
        return positionError * attractiveGain;
    }

    Vector3 CalculateRepulsiveForce(Vector3 toUser, float distanceToUser)
    {
        // If user is far away, no repulsive force (Smooth fade out)
        if (distanceToUser >= avoidanceRadius)
            return Vector3.zero;

        // Direction away from user
        Vector3 awayDirection = -toUser.normalized;
        
        // Add upward component to fly "over" or around the user naturally
        awayDirection += Vector3.up * 0.3f; 
        awayDirection.Normalize();

        // Calculate "Danger Factor" (0.0 at edge of radius, 1.0 at safety buffer)
        float dangerRange = avoidanceRadius - safetyBuffer;
        float dangerFactor = (avoidanceRadius - distanceToUser) / dangerRange;
        dangerFactor = Mathf.Clamp01(dangerFactor);

        // Quadratic falloff: Weak force at 3m, Strong force at 1m
        // This prevents the "impulsive hit" feeling
        float magnitude = repulsiveGain * (dangerFactor * dangerFactor);

        return awayDirection * magnitude;
    }
}
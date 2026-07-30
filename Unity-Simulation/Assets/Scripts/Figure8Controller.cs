using UnityEngine;

public class Figure8Controller : MonoBehaviour
{
    [Header("Trajectory Parameters")]
    public float speed = 0.5f;
    public float radius = 2.0f;
    public float height = 2.5f; 

    [Header("APF Gains (Tune these)")]
    public float attractiveGain = 4.0f;  
    public float repulsiveGain = 12.0f;  
    public float dampingGain = 1.5f;     

    [Header("Altitude Hold Gains (Crucial for real hardware)")]
    public float altitudePGain = 10.0f;  // Pulls drone to target height
    public float altitudeDGain = 4.0f;   // Dampens vertical bouncing

    [Header("Avoidance Settings")]
    public Transform userHead;
    public float avoidanceRadius = 3.0f; 
    public float safetyBuffer = 1.0f;    

    private Rigidbody rb;
    private float time;
    private Vector3 centerOffset;

    void Start()
    {
        rb = GetComponent<Rigidbody>();
        rb.useGravity = true;
        rb.linearDamping = 0.2f; // Lowered slightly so altitude hold does the work
        
        centerOffset = transform.position;
        centerOffset.y = height;
    }

    void FixedUpdate()
    {
        if (userHead == null) return;

        // 1. Calculate Horizontal Forces (Trajectory + Avoidance)
        Vector3 attractiveForce = CalculateAttractiveForce();
        
        Vector3 toUser = userHead.position - transform.position;
        float distanceToUser = toUser.magnitude;
        Vector3 repulsiveForce = CalculateRepulsiveForce(toUser, distanceToUser);

        // 2. Calculate Damping Force (Braking - X and Z only)
        Vector3 horizontalVelocity = rb.linearVelocity;
        horizontalVelocity.y = 0; // Don't dampen vertical velocity, let altitude hold handle it
        Vector3 dampingForce = -horizontalVelocity * dampingGain;

        // 3. Calculate Altitude Hold Force (Y axis only)
        Vector3 altitudeForce = CalculateAltitudeHoldForce();

        // 4. Combine Forces
        Vector3 totalForce = attractiveForce + repulsiveForce + dampingForce + altitudeForce;

        // Apply Force
        rb.AddForce(totalForce, ForceMode.Force);
    }

    Vector3 CalculateAttractiveForce()
    {
        time += speed * Time.fixedDeltaTime;
        
        float x = radius * Mathf.Sin(time);
        float z = radius * Mathf.Sin(time) * Mathf.Cos(time);
        
        // Target position on the Figure-8
        Vector3 targetPosition = centerOffset + new Vector3(x, 0, z);

        // Only pull horizontally toward the path
        Vector3 positionError = targetPosition - transform.position;
        positionError.y = 0; // <--- CRITICAL: Do not use Y for horizontal attraction

        return positionError * attractiveGain;
    }

    Vector3 CalculateRepulsiveForce(Vector3 toUser, float distanceToUser)
    {
        if (distanceToUser >= avoidanceRadius)
            return Vector3.zero;

        // FLATTEN the vector to the horizontal plane (XZ only)
        Vector3 awayDirection = -toUser;
        awayDirection.y = 0; // <--- CRITICAL: No vertical avoidance!
        awayDirection.Normalize();

        float dangerRange = avoidanceRadius - safetyBuffer;
        float dangerFactor = (avoidanceRadius - distanceToUser) / dangerRange;
        dangerFactor = Mathf.Clamp01(dangerFactor);

        // Quadratic falloff for smooth pushing
        float magnitude = repulsiveGain * (dangerFactor * dangerFactor);

        return awayDirection * magnitude;
    }

    Vector3 CalculateAltitudeHoldForce()
    {
        // Calculate error in height
        float heightError = height - transform.position.y;
        
        // Calculate error in vertical velocity (to prevent bouncing)
        float verticalVelocityError = -rb.linearVelocity.y;

        // PID-like calculation for vertical force
        float verticalForce = (heightError * altitudePGain) + (verticalVelocityError * altitudeDGain);

        // Add gravity compensation (Feedforward)
        // This calculates the exact force needed to counteract gravity
        float gravityCompensation = rb.mass * Mathf.Abs(Physics.gravity.y);

        verticalForce += gravityCompensation;

        return Vector3.up * verticalForce;
    }
}
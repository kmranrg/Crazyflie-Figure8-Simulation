using UnityEngine;

public class Figure8Controller : MonoBehaviour
{
    [Header("Trajectory Parameters")]
    public float speed = 0.5f;
    public float radius = 2.0f;
    public float height = 1.5f;

    [Header("PID Controller Gains")]
    public float proportionalGain = 5.0f;
    public float derivativeGain = 2.0f;

    [Header("Avoidance Settings")]
    public Transform userHead; // Drag the VR Camera here
    public float avoidanceRadius = 1.5f; // Distance to trigger avoidance
    public float avoidanceForce = 15.0f; // How hard it pushes away
    public float safeDistance = 2.0f; // Distance to resume normal flight

    private Rigidbody rb;
    private float time;
    private Vector3 centerOffset;
    private bool isAvoiding = false;

    void Start()
    {
        rb = GetComponent<Rigidbody>();
        rb.useGravity = true;
        
        centerOffset = transform.position;
        centerOffset.y = height;
    }

    void FixedUpdate()
    {
        if (userHead == null) return;

        // Calculate distance to user
        Vector3 toUser = userHead.position - transform.position;
        float distanceToUser = toUser.magnitude;

        // Check if we need to avoid
        if (distanceToUser < avoidanceRadius)
        {
            isAvoiding = true;
            ApplyAvoidanceForce(toUser);
        }
        else if (distanceToUser > safeDistance)
        {
            isAvoiding = false;
            ApplyTrajectoryForce();
        }
        else
        {
            // Hysteresis: If we are avoiding, keep avoiding until we are fully safe
            if (isAvoiding)
            {
                ApplyAvoidanceForce(toUser);
            }
            else
            {
                ApplyTrajectoryForce();
            }
        }
    }

    void ApplyTrajectoryForce()
    {
        time += speed * Time.fixedDeltaTime;

        float x = radius * Mathf.Sin(time);
        float z = radius * Mathf.Sin(time) * Mathf.Cos(time);

        Vector3 targetPosition = centerOffset + new Vector3(x, 0, z);

        Vector3 positionError = targetPosition - transform.position;
        Vector3 velocityError = -rb.linearVelocity;

        Vector3 controlForce = (positionError * proportionalGain) + (velocityError * derivativeGain);
        
        rb.AddForce(controlForce, ForceMode.Force);
    }

    void ApplyAvoidanceForce(Vector3 toUser)
    {
        // Calculate direction away from user
        Vector3 awayDirection = -toUser.normalized;
        
        // Add an upward component to fly "over" or around the user
        awayDirection += Vector3.up * 0.5f; 
        awayDirection.Normalize();

        // Apply strong repulsive force
        rb.AddForce(awayDirection * avoidanceForce, ForceMode.Force);
    }
}
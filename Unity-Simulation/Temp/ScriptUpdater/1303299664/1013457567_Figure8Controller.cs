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

    private Rigidbody rb;
    private float time;
    private Vector3 centerOffset;

    void Start()
    {
        rb = GetComponent<Rigidbody>();
        rb.useGravity = true;
        
        centerOffset = transform.position;
        centerOffset.y = height;
    }

    void FixedUpdate()
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
}